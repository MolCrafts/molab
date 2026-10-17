import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Table2 } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { useEffect, useMemo } from "react";
import { EmptyState } from "@/app/components/entity";
import { ROW_PADDING_DEFAULT } from "@/app/components/entity/density";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RunStatusBadge, WorkbenchIconAction } from "@/components/workbench";
import { formatDuration, formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";

import {
  computeRunDurationSeconds,
  type JobsSort,
  type JobsSortKey,
  nextJobsSort,
  PAGE_SIZE_OPTIONS,
  paginate,
  sortJobs,
} from "./jobsTable";
import { runExecutorFacetLabel, runPresentationStatus } from "./projections";
import type { WorkspaceRunRow } from "./types";

/**
 * Optional tick column for gathering runs into the comparison set.
 *
 * Ticking is additive and never navigates, so a user can keep opening runs to
 * inspect them while building a set — the row click still means "open".
 * Indices are into the table's current sort order, which is what a shift-range
 * has to follow to match what the eye sees.
 */
export interface RunsTableSelection {
  selected: ReadonlySet<string>;
  /**
   * Apply a tick. The table supplies both the index and the id order it refers
   * to, because the table owns the sort — a caller passing its own unsorted
   * list would resolve a shift-range to entirely different rows than the ones
   * the user dragged across.
   */
  selectAt: (
    index: number,
    orderedIds: string[],
    modifiers: { shift: boolean; meta: boolean },
  ) => void;
}

interface RunsJobsTableProps {
  rows: WorkspaceRunRow[];
  selectedRunId: string | null;
  onSelectRun: (run: WorkspaceRunRow) => void;
  selection?: RunsTableSelection;
  sort: JobsSort;
  onSortChange: (next: JobsSort) => void;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

interface ColumnDef {
  key: JobsSortKey;
  label: string;
  align?: "left" | "right";
  className?: string;
}

// Fixed layout: an auto table sizes every column to its longest cell, so one
// long run name pushed Attempts / Duration off the right edge and `truncate`
// never fired. Run takes what the fixed columns leave (at least ~13rem: the
// table scrolls sideways before it squeezes run names), and wraps.
const COLUMNS: ColumnDef[] = [
  { key: "status", label: "Status", className: "w-30" },
  { key: "name", label: "Run" },
  { key: "project", label: "Project · Experiment", className: "w-44" },
  { key: "backend", label: "Backend", className: "w-24" },
  { key: "attempts", label: "Attempts", align: "right", className: "w-24" },
  { key: "duration", label: "Duration", align: "right", className: "w-24" },
  { key: "submitted", label: "Submitted", align: "right", className: "w-26" },
];

/**
 * Workspace Jobs table — sortable columns + client-side pagination.
 * Sort / page state is owned by the parent (URL-backed).
 */
export const RunsJobsTable = ({
  rows,
  selectedRunId,
  onSelectRun,
  sort,
  onSortChange,
  selection,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: RunsJobsTableProps): JSX.Element => {
  const sorted = useMemo(() => sortJobs(rows, sort), [rows, sort]);
  const sortedIds = useMemo(() => sorted.map((run) => run.id), [sorted]);
  const sortedIndex = useMemo(
    () => new Map(sortedIds.map((id, index) => [id, index] as const)),
    [sortedIds],
  );
  const slice = useMemo(() => paginate(sorted, page, pageSize), [sorted, page, pageSize]);

  // Parent may still hold a page past the end after a filter shrink.
  useEffect(() => {
    if (slice.page !== page) onPageChange(slice.page);
  }, [slice.page, page, onPageChange]);

  if (rows.length === 0) {
    return (
      <div className="flex h-full min-h-60 items-center justify-center border-y border-dashed border-border/70">
        <EmptyState
          icon={<Table2 className="size-icon-lg" />}
          title="No matching runs"
          description="Adjust filters in the sidebar, or clear them to see the full workspace."
        />
      </div>
    );
  }

  const rangeStart = slice.totalItems === 0 ? 0 : (slice.page - 1) * slice.pageSize + 1;
  const rangeEnd = Math.min(slice.page * slice.pageSize, slice.totalItems);

  return (
    <div className="flex flex-col gap-3">
      <div className="border-y border-border/70">
        <Table className="w-full min-w-[58rem] table-fixed text-body">
          <TableHeader className="sticky top-0 z-10 border-b border-border/60 bg-background">
            <TableRow className="text-label text-muted-foreground">
              {selection && <TableHead className="w-10" aria-label="Select" />}
              {COLUMNS.map((col) => (
                <SortableTh
                  key={col.key}
                  column={col}
                  active={sort.key === col.key}
                  dir={sort.dir}
                  onClick={() => onSortChange(nextJobsSort(sort, col.key))}
                />
              ))}
            </TableRow>
          </TableHeader>
          <TableBody className="divide-y divide-border/50">
            {slice.items.map((run) => {
              const isSelected = run.id === selectedRunId;
              const duration = computeRunDurationSeconds(run);
              const presentationStatus = runPresentationStatus(run);
              const backend = runExecutorFacetLabel(run, "backend");
              const cluster = runExecutorFacetLabel(run, "cluster_name");
              return (
                <TableRow
                  key={run.id}
                  tabIndex={0}
                  aria-label={`Open run ${run.name || run.id}`}
                  aria-selected={isSelected}
                  onClick={() => onSelectRun(run)}
                  onKeyDown={(event) => {
                    if (
                      event.target !== event.currentTarget ||
                      (event.key !== "Enter" && event.key !== " ")
                    ) {
                      return;
                    }
                    event.preventDefault();
                    onSelectRun(run);
                  }}
                  className={cn(
                    "cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                    isSelected ? "bg-accent/5" : "hover:bg-muted/40",
                  )}
                >
                  {selection && (
                    <Td className="align-middle">
                      {/* Stop propagation: ticking gathers, it does not open. */}
                      <Checkbox
                        checked={selection.selected.has(run.id)}
                        aria-label={`${
                          selection.selected.has(run.id) ? "Remove" : "Add"
                        } run ${run.name || run.id}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          selection.selectAt(sortedIndex.get(run.id) ?? 0, sortedIds, {
                            shift: event.shiftKey,
                            meta: !event.shiftKey,
                          });
                        }}
                      />
                    </Td>
                  )}
                  <Td className="align-middle">
                    <RunStatusBadge status={presentationStatus} size="sm" />
                  </Td>
                  <Td className="align-middle">
                    <div className="min-w-0">
                      <p className="font-medium text-foreground [overflow-wrap:anywhere]">
                        {run.name || run.id}
                      </p>
                      <p
                        className="mt-1 truncate font-mono text-micro text-muted-foreground"
                        title={run.id}
                      >
                        {run.id}
                      </p>
                    </div>
                  </Td>
                  <Td className="align-middle text-muted-foreground">
                    <div className="min-w-0">
                      <p className="truncate text-foreground">{run.projectName}</p>
                      <p className="truncate text-label">{run.experimentName}</p>
                    </div>
                  </Td>
                  <Td className="align-middle text-muted-foreground">
                    {backend ? (
                      <div className="min-w-0">
                        <p className="truncate text-foreground">{backend}</p>
                        {cluster && <p className="truncate font-mono text-micro">{cluster}</p>}
                      </div>
                    ) : (
                      <span>—</span>
                    )}
                  </Td>
                  <Td className="text-right align-middle tabular-nums text-muted-foreground">
                    {run.statusSummary.total}
                  </Td>
                  <Td className="whitespace-nowrap text-right align-middle font-mono text-label tabular-nums text-muted-foreground">
                    {formatDuration(duration)}
                  </Td>
                  <Td className="text-right align-middle text-label text-muted-foreground">
                    {formatRelative(run.createdAt)}
                  </Td>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-label text-muted-foreground">
        <div className="tabular-nums">
          {rangeStart}–{rangeEnd} of {slice.totalItems}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2">
            <span>Rows</span>
            <Select
              value={String(pageSize)}
              onValueChange={(value) => onPageSizeChange(Number.parseInt(value, 10))}
            >
              <SelectTrigger size="sm" className="w-18" aria-label="Rows per page">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1">
            <WorkbenchIconAction
              label="Previous page"
              type="button"
              disabled={slice.page <= 1}
              onClick={() => onPageChange(slice.page - 1)}
            >
              <ChevronLeft className="size-icon-sm" />
            </WorkbenchIconAction>
            <span className="min-w-18 text-center tabular-nums">
              {slice.page} / {slice.totalPages}
            </span>
            <WorkbenchIconAction
              label="Next page"
              type="button"
              disabled={slice.page >= slice.totalPages}
              onClick={() => onPageChange(slice.page + 1)}
            >
              <ChevronRight className="size-icon-sm" />
            </WorkbenchIconAction>
          </div>
        </div>
      </div>
    </div>
  );
};

const SortableTh = ({
  column,
  active,
  dir,
  onClick,
}: {
  column: ColumnDef;
  active: boolean;
  dir: JobsSort["dir"];
  onClick: () => void;
}): JSX.Element => {
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      className={cn(
        `${ROW_PADDING_DEFAULT} font-medium`,
        column.align === "right" ? "text-right" : "text-left",
        column.className,
      )}
    >
      <span
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-foreground",
          column.align === "right" && "flex-row-reverse",
          active ? "text-foreground" : "text-muted-foreground",
        )}
      >
        <span>{column.label}</span>
        <WorkbenchIconAction
          label={`Sort by ${column.label}${active ? `, currently ${dir}` : ""}`}
          size="compact"
          onClick={onClick}
          className="size-icon-lg text-current"
        >
          <Icon className="size-3 opacity-70" aria-hidden="true" />
        </WorkbenchIconAction>
      </span>
    </TableHead>
  );
};

const Td = ({ children, className }: { children: ReactNode; className?: string }): JSX.Element => (
  <TableCell className={cn(ROW_PADDING_DEFAULT, className)}>{children}</TableCell>
);
