/**
 * Experiment Runs (Figma L03-3 … L03-5): one 24px row per run — status glyph,
 * its title, each swept numeric value, time, the key results, target, id.
 * A filter bar (`status:` `driver:` `timestep_fs>`), sortable columns, and
 * selection by checkbox or ⌘ / ⇧ click, which swaps the filter bar for the
 * selection bar. A click previews the run (L12), double-click or ↵ opens it,
 * ↑↓ moves the preview.
 */

import { ChevronDown, ChevronUp, ListFilter, Server, X } from "lucide-react";
import { type JSX, type KeyboardEvent, type MouseEvent, useMemo, useState } from "react";
import { nextSelection } from "@/app/compare/nextSelection";
import { EmptyState, formatSpan, StatusIcon } from "@/app/components/entity";
import { varyingParameterKeys } from "@/app/renderers/entityWorkbenchData";
import { attemptSeconds, attemptTarget, formatFigure } from "@/app/renderers/run/runStory";
import { useRunSiblings } from "@/app/renderers/run/useRunSiblings";
import { filterRuns } from "@/app/runs/runsFilter";
import { formatParameterValue, parameterUnit, runLabel } from "@/app/runs/runTitle";
import { SelectionActions } from "@/app/runs/SelectionActions";
import { normalizeStatus, STATUS } from "@/app/status/vocabulary";
import type { RunSummary } from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

/** Key-result columns shown at most. */
const MAX_RESULT_COLUMNS = 2;

interface Row {
  run: RunSummary;
  title: string;
  seconds: number | null;
  target: string | null;
  results: Record<string, unknown>;
}

type SortKey = { column: string; dir: 1 | -1 };

const STATUS_ORDER = [
  "failed",
  "interrupted",
  "running",
  "finalizing",
  "queued",
  "pending",
  "cancelled",
  "succeeded",
] as const;

const compare = (left: unknown, right: unknown): number => {
  if (left === right) return 0;
  if (left === null || left === undefined) return 1;
  if (right === null || right === undefined) return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), undefined, { numeric: true });
};

/** The value a column sorts by. */
const cellValue = (row: Row, column: string): unknown => {
  if (column === "run") return row.title;
  if (column === "status") return STATUS_ORDER.indexOf(normalizeStatus(row.run.status) as never);
  if (column === "time") return row.seconds;
  if (column === "target") return row.target;
  if (column === "id") return row.run.id;
  if (column.startsWith("p:")) return row.run.parameters?.[column.slice(2)];
  if (column.startsWith("r:")) return row.results[column.slice(2)];
  return null;
};

export interface ExperimentRunsTableProps {
  runs: readonly RunSummary[];
  experimentId: string;
  filter: string;
  onFilterChange: (next: string) => void;
  onPreview: (run: RunSummary) => void;
  onOpen: (run: RunSummary, background?: boolean) => void;
  compareDisabledReason: string | null;
  onCompare: (runs: readonly RunSummary[]) => void;
  onChanged: () => void;
}

export const ExperimentRunsTable = ({
  runs,
  experimentId,
  filter,
  onFilterChange,
  onPreview,
  onOpen,
  compareDisabledReason,
  onCompare,
  onChanged,
}: ExperimentRunsTableProps): JSX.Element => {
  const { siblings } = useRunSiblings({ id: "", experimentId }, { results: runs.length > 0 });
  const resultsOf = useMemo(
    () => new Map(siblings.map((sibling) => [sibling.id, sibling.results ?? {}])),
    [siblings],
  );
  const rows = useMemo(
    (): Row[] =>
      runs.map((run) => {
        const latest = run.executionHistory.at(-1);
        return {
          run,
          title: runLabel(run),
          seconds: latest ? attemptSeconds(latest) : null,
          target: attemptTarget(latest),
          results: resultsOf.get(run.id) ?? {},
        };
      }),
    [runs, resultsOf],
  );
  // Swept numeric values get columns; words already read in the title.
  const sweptColumns = useMemo(
    () =>
      varyingParameterKeys(runs.map((run) => ({ parameters: run.parameters ?? {} })))
        .filter((key) => runs.some((run) => typeof run.parameters?.[key] === "number"))
        .sort(),
    [runs],
  );
  const resultColumns = useMemo(() => {
    const seen: string[] = [];
    for (const row of rows) {
      for (const [key, value] of Object.entries(row.results)) {
        if (typeof value === "number" && !seen.includes(key)) seen.push(key);
      }
    }
    return seen.slice(0, MAX_RESULT_COLUMNS);
  }, [rows]);

  // Until a header is clicked, rows sort by the first swept value (the sweep's own order).
  const [sortChoice, setSort] = useState<SortKey | null>(null);
  const sort: SortKey = sortChoice ?? {
    column: sweptColumns[0] ? `p:${sweptColumns[0]}` : "run",
    dir: 1,
  };
  const shown = useMemo(() => {
    const filtered = filterRuns(
      rows.map((row) => ({
        ...row,
        id: row.run.id,
        status: row.run.status,
        parameters: row.run.parameters ?? {},
      })),
      filter,
    );
    return [...filtered].sort(
      (left, right) =>
        compare(cellValue(left, sort.column), cellValue(right, sort.column)) * sort.dir ||
        compare(left.title, right.title),
    );
  }, [rows, filter, sort]);

  const order = useMemo(() => shown.map((row) => row.run.id), [shown]);
  const [selection, setSelection] = useState<{ selected: Set<string>; anchor: number | null }>({
    selected: new Set(),
    anchor: null,
  });
  const selected = runs.filter((run) => selection.selected.has(run.id));
  const select = (index: number, modifiers: { shift: boolean; meta: boolean }): void =>
    setSelection((current) => nextSelection(current, index, order, modifiers));
  const [focused, setFocused] = useState<string | null>(null);

  const onRowClick = (event: MouseEvent, row: Row, index: number): void => {
    if (event.metaKey || event.ctrlKey || event.shiftKey) {
      select(index, { shift: event.shiftKey, meta: event.metaKey || event.ctrlKey });
      return;
    }
    setFocused(row.run.id);
    onPreview(row.run);
  };
  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, row: Row, index: number): void => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = shown[index + (event.key === "ArrowDown" ? 1 : -1)];
      const element =
        event.key === "ArrowDown"
          ? event.currentTarget.nextElementSibling
          : event.currentTarget.previousElementSibling;
      if (next && element instanceof HTMLElement) {
        element.focus();
        setFocused(next.run.id);
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

  const header = (column: string, label: string, numeric = false, title?: string) => {
    const active = sort.column === column;
    const Arrow = sort.dir === 1 ? ChevronUp : ChevronDown;
    return (
      <th
        key={column}
        scope="col"
        className={cn("h-list-row px-list-pad-x font-normal", numeric ? "text-right" : "text-left")}
        aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
      >
        <button
          type="button"
          title={title}
          onClick={() =>
            setSort(() => ({
              column,
              dir: sort.column === column ? (sort.dir === 1 ? -1 : 1) : 1,
            }))
          }
          className={cn(
            "inline-flex items-center gap-hairline rounded-hairline hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            numeric && "flex-row-reverse",
            active && "text-foreground",
          )}
        >
          {label}
          {active ? <Arrow aria-hidden className="size-3" /> : null}
        </button>
      </th>
    );
  };

  const allSelected = shown.length > 0 && shown.every((row) => selection.selected.has(row.run.id));

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div
        className={cn(
          "flex h-9 shrink-0 items-center gap-2 px-6",
          selected.length > 0 && "bg-accent-muted",
        )}
      >
        {selected.length > 0 ? (
          <SelectionActions
            runs={selected}
            compareDisabledReason={compareDisabledReason}
            onCompare={() => onCompare(selected)}
            onClear={() => setSelection({ selected: new Set(), anchor: null })}
            onChanged={() => {
              setSelection({ selected: new Set(), anchor: null });
              onChanged();
            }}
          />
        ) : (
          <>
            <label className="flex h-6 w-96 max-w-full items-center gap-1 rounded-hairline border border-border bg-background px-2 focus-within:border-ring">
              <ListFilter aria-hidden className="size-icon-sm shrink-0 text-muted-foreground" />
              <input
                type="search"
                aria-label="Filter runs"
                placeholder="Filter  status:  driver:  timestep_fs>"
                value={filter}
                onChange={(event) => onFilterChange(event.target.value)}
                className="min-w-0 flex-1 bg-transparent font-mono text-label text-foreground outline-none placeholder:font-sans placeholder:text-muted-foreground"
              />
              {filter ? (
                <WorkbenchIconAction label="Clear filter" onClick={() => onFilterChange("")}>
                  <X aria-hidden className="size-icon-sm" />
                </WorkbenchIconAction>
              ) : null}
            </label>
            <span className="text-label tabular-nums text-muted-foreground">
              {filter ? `${shown.length} of ${runs.length} runs` : `${runs.length} runs`}
            </span>
          </>
        )}
      </div>
      {runs.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-6">
          <EmptyState title="No runs" description="New run or Sweep from the editor actions." />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table aria-label="Runs" className="w-full min-w-[44rem] border-collapse text-body">
            <thead className="sticky top-0 z-10 border-b border-border bg-background text-label text-muted-foreground">
              <tr>
                <th scope="col" className="h-list-row w-10 pl-6">
                  <input
                    type="checkbox"
                    aria-label={allSelected ? "Deselect all runs" : "Select all runs"}
                    checked={allSelected}
                    onChange={() =>
                      setSelection({
                        selected: allSelected ? new Set() : new Set(shown.map((row) => row.run.id)),
                        anchor: null,
                      })
                    }
                    className="size-3.5 accent-accent"
                  />
                </th>
                {header("status", "", false, "Sort by status")}
                {header("run", "run")}
                {sweptColumns.map((key) => header(`p:${key}`, key, true))}
                {header("time", "time", true)}
                {resultColumns.map((key) => header(`r:${key}`, key, true))}
                {header("target", "target")}
                {header("id", "id")}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 ? (
                <tr>
                  <td
                    colSpan={6 + sweptColumns.length + resultColumns.length}
                    className="px-6 py-4 text-muted-foreground"
                  >
                    No run matches “{filter}”.
                  </td>
                </tr>
              ) : null}
              {shown.map((row, index) => {
                const isSelected = selection.selected.has(row.run.id);
                const isFocused = focused === row.run.id;
                return (
                  <tr
                    key={row.run.id}
                    tabIndex={0}
                    aria-selected={isSelected}
                    aria-label={`${row.title} · ${STATUS[normalizeStatus(row.run.status)].word}`}
                    onClick={(event) => onRowClick(event, row, index)}
                    onDoubleClick={(event) => {
                      if ((event.target as HTMLElement).closest("input")) return;
                      onOpen(row.run);
                    }}
                    onKeyDown={(event) => onRowKey(event, row, index)}
                    className={cn(
                      "h-list-row cursor-default outline-none hover:bg-interactive focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                      isSelected && "bg-accent-muted hover:bg-accent-muted",
                      isFocused &&
                        !isSelected &&
                        "bg-interactive shadow-[inset_2px_0_0_var(--molab-accent)]",
                    )}
                  >
                    <td className="pl-6">
                      <input
                        type="checkbox"
                        aria-label={`${isSelected ? "Deselect" : "Select"} ${row.title}`}
                        checked={isSelected}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) =>
                          select(index, {
                            shift:
                              (event.nativeEvent as unknown as globalThis.MouseEvent).shiftKey ??
                              false,
                            meta: true,
                          })
                        }
                        className="size-3.5 accent-accent"
                      />
                    </td>
                    <td className="w-6 px-list-pad-x">
                      <StatusIcon status={row.run.status} className="size-icon-sm" />
                    </td>
                    <td
                      className="max-w-[18rem] truncate px-list-pad-x font-mono"
                      title={row.title}
                    >
                      {row.title}
                    </td>
                    {sweptColumns.map((key) => (
                      <td key={key} className="px-list-pad-x text-right font-mono tabular-nums">
                        {row.run.parameters && key in row.run.parameters
                          ? formatParameterValue(key, row.run.parameters[key]).replace(
                              ` ${parameterUnit(key) ?? "\u0000"}`,
                              "",
                            )
                          : "—"}
                      </td>
                    ))}
                    <td className="px-list-pad-x text-right tabular-nums">
                      {row.seconds === null ? "—" : formatSpan(row.seconds)}
                    </td>
                    {resultColumns.map((key) => {
                      const value = row.results[key];
                      return (
                        <td key={key} className="px-list-pad-x text-right font-mono tabular-nums">
                          {typeof value === "number" ? formatFigure(value) : "—"}
                        </td>
                      );
                    })}
                    <td className="px-list-pad-x text-muted-foreground">
                      {row.target ? (
                        <span className="inline-flex items-center gap-1">
                          <Server aria-hidden className="size-icon-sm" />
                          {row.target}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-list-pad-x pr-6 font-mono text-label text-muted-foreground">
                      {row.run.id}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
