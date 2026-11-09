/**
 * Attempts view (Figma L04-7): one row per attempt, newest first — glyph · id ·
 * mode · based on · target · started · time · tasks reused / run. A click
 * previews the attempt (L12); a double-click or ↵ selects it for the page, and
 * every view then follows it. Below the list, what the page's attempt left:
 * its failure, products, files, workflow graph and executor.
 */

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@molcrafts/ui";
import { useQueries, useQuery } from "@tanstack/react-query";
import { type JSX, type KeyboardEvent, useMemo, useState } from "react";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import { EmptyState, formatSpan, PropertyList, StatusIcon } from "@/app/components/entity";
import { listExecutionColumns, listExecutionDetails } from "@/app/registry";
import {
  failedTask,
  failureHeadline,
  failureRecovery,
  preferredFailureOutput,
} from "@/app/renderers/run/executionFailure";
import { RunExecutionOutputs } from "@/app/renderers/run/RunExecutionOutputs";
import { attemptSeconds, attemptTarget, clockOf } from "@/app/renderers/run/runStory";
import { TaskProductList } from "@/app/renderers/run/TaskProductList";
import { taskProducts } from "@/app/renderers/run/taskProducts";
import { PruneDialog } from "@/app/runs/PruneDialog";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import { normalizeStatus, statusWord } from "@/app/status/vocabulary";
import type { ExecutionRecordSummary, RunSummary, WorkflowSummary } from "@/app/types";
import { WorkbenchOperationState } from "@/components/workbench";
import { normalizeTaskGraph } from "@/components/workflow/flowgram-document";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";
import { WorkflowGraph } from "@/components/workflow/workflow-graph";
import type { ExecutionRowData } from "@/lib/contribution-types";
import { cn } from "@/lib/utils";

/** Same section head as the other run views: a name on a hairline. */
const SectionHead = ({ title }: { title: string }): JSX.Element => (
  <h3 className="border-b border-border pb-1 text-body text-foreground">{title}</h3>
);

const stringValue = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

const backendOf = (execution: ExecutionRecordSummary): string =>
  stringValue(execution.executor.backend) ?? stringValue(execution.executor.target) ?? "local";

const executionRow = (execution: ExecutionRecordSummary, runId: string): ExecutionRowData => ({
  executionId: execution.executionId,
  runId,
  status: execution.status,
  startedAt: execution.startedAt ?? execution.createdAt,
  finishedAt: execution.finishedAt,
  durationSeconds: null,
  schedulerJobId:
    stringValue(execution.executor.scheduler_job_id) ?? stringValue(execution.executor.job_id),
  backend: backendOf(execution),
  metadata: Object.fromEntries(
    Object.entries(execution.executor).map(([key, value]) => [
      key,
      typeof value === "string" ? value : JSON.stringify(value),
    ]),
  ),
});

/** "1 reused · 2 run", or "1 of 3" when not every task ran: what the attempt did. */
export const attemptTasksText = (graph: TaskGraphJson | null | undefined): string => {
  const tasks = graph?.task_configs ?? [];
  if (tasks.length === 0) return "—";
  const statuses = tasks.map((task) => normalizeStatus(task.status ?? "pending"));
  const reused = statuses.filter((status) => status === "cached").length;
  const done = statuses.filter((status) => status === "succeeded").length;
  if (reused > 0) return `${reused} reused · ${done} run`;
  return done === tasks.length ? `${done} run` : `${done} of ${tasks.length}`;
};

/** Module-level so TanStack re-runs it only when a journal changes. */
const combineJournals = (queries: readonly { data?: unknown }[]) =>
  queries.map((item) => (item.data ? normalizeTaskGraph(item.data as never) : null));

interface RunAttemptsPanelProps {
  run: RunSummary;
  workflow?: WorkflowSummary;
  /** The attempt the page shows. */
  selectedExecutionId: string | null;
  /** Make an attempt the page's (↵ / double-click). */
  onSelectExecution: (executionId: string) => void;
  /** Preview an attempt (single click). */
  onPreviewExecution: (executionId: string) => void;
  onInspectTask: (taskId: string, runId: string) => void;
  onOpenWorkflow?: () => void;
  outputs: ExecutionOutputsResponse | null;
  logsError: string | null;
  onPromoted?: () => void;
}

/** 22px rows (DS density): no cell padding beyond the gutter. */
const CELL = "h-6 px-2 py-0 text-body font-normal whitespace-nowrap";

export const RunAttemptsPanel = ({
  run,
  workflow,
  selectedExecutionId,
  onSelectExecution,
  onPreviewExecution,
  onInspectTask,
  onOpenWorkflow,
  outputs,
  logsError,
  onPromoted,
}: RunAttemptsPanelProps): JSX.Element => {
  const history = run.executionHistory;
  const newestFirst = useMemo(() => [...history].reverse(), [history]);
  const journals = useQueries({
    queries: newestFirst.map((execution) => ({
      ...executionJournalQueryOptions(
        run.projectId,
        run.experimentId,
        run.id,
        execution.executionId,
      ),
      refetchInterval: journalRefetchInterval(execution.status),
    })),
    combine: combineJournals,
  });
  const selected = history.find((item) => item.executionId === selectedExecutionId) ?? null;
  const journal = useQuery({
    ...executionJournalQueryOptions(
      run.projectId,
      run.experimentId,
      run.id,
      selectedExecutionId ?? "",
    ),
    enabled: selectedExecutionId !== null,
    refetchInterval: journalRefetchInterval(selected?.status),
  });
  const graph = journal.data ? normalizeTaskGraph(journal.data) : null;
  const graphError = journal.error
    ? journal.error instanceof Error
      ? journal.error.message
      : "Failed to load execution workflow"
    : null;
  const graphLoading = journal.isLoading;
  const [pinned, setPinned] = useState<{ executionId: string; path: string } | null>(null);
  const pinnedPath =
    pinned && selected && pinned.executionId === selected.executionId ? pinned.path : null;
  const products = useMemo(
    () => (graph && selected ? taskProducts(graph.task_configs, selected.executionId) : []),
    [graph, selected],
  );
  const taskFailure = failedTask(graph);
  const headline = selected
    ? failureHeadline({ status: selected.status, error: selected.error, task: taskFailure })
    : null;
  const failureSelection = headline
    ? preferredFailureOutput(taskFailure?.id ?? null, outputs)
    : null;
  const recovery = headline ? failureRecovery(failureSelection) : null;
  const row = selected ? executionRow(selected, run.id) : null;
  const columns = useMemo(() => listExecutionColumns(row?.backend), [row?.backend]);
  const details = useMemo(() => listExecutionDetails(row?.backend), [row?.backend]);

  if (history.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background px-6">
        <EmptyState title="No attempts" description="Start the run to create its first attempt." />
      </div>
    );
  }

  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, executionId: string): void => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      // ↑↓ moves through the attempts and the Preview follows (focus stays in the table).
      event.preventDefault();
      const row =
        event.key === "ArrowDown"
          ? event.currentTarget.nextElementSibling
          : event.currentTarget.previousElementSibling;
      if (row instanceof HTMLElement) {
        row.focus();
        row.click();
      }
    } else if (event.key === "Enter") {
      event.preventDefault();
      onSelectExecution(executionId);
    } else if (event.key === " ") {
      event.preventDefault();
      onPreviewExecution(executionId);
    }
  };

  return (
    <div className="h-full min-h-0 overflow-auto bg-background">
      <Table aria-label="Attempts" className="min-w-[44rem] text-body">
        <TableHeader>
          <TableRow className="h-7 border-border hover:bg-transparent">
            <TableHead className={cn(CELL, "w-8")}>
              <span className="sr-only">Status</span>
            </TableHead>
            <TableHead className={CELL}>attempt</TableHead>
            <TableHead className={CELL}>mode</TableHead>
            <TableHead className={CELL}>based on</TableHead>
            <TableHead className={CELL}>target</TableHead>
            <TableHead className={CELL}>started</TableHead>
            <TableHead className={CELL}>time</TableHead>
            <TableHead className={CELL}>tasks</TableHead>
            <TableHead className={cn(CELL, "w-8 pr-4")}>
              <PruneDialog run={run} onPruned={onPromoted} />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {newestFirst.map((execution, index) => {
            const current = execution.executionId === selectedExecutionId;
            const seconds = attemptSeconds(execution);
            return (
              <TableRow
                key={execution.executionId}
                tabIndex={0}
                aria-selected={current}
                aria-label={`${execution.executionId} · ${statusWord(execution.status)}`}
                title="Click to preview · double-click or ↵ to show this attempt"
                onClick={() => onPreviewExecution(execution.executionId)}
                onDoubleClick={() => onSelectExecution(execution.executionId)}
                onKeyDown={(event) => onRowKey(event, execution.executionId)}
                className={cn(
                  "h-6 cursor-default border-0 text-foreground outline-none",
                  "hover:bg-interactive focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                  current && "bg-accent-muted hover:bg-accent-muted",
                )}
              >
                <TableCell className={cn(CELL, "pl-4")}>
                  <StatusIcon status={execution.status} className="size-icon-sm" />
                </TableCell>
                <TableCell className={cn(CELL, "font-mono")}>{execution.executionId}</TableCell>
                <TableCell className={CELL}>{execution.mode}</TableCell>
                <TableCell className={cn(CELL, "font-mono text-muted-foreground")}>
                  {execution.basedOnExecutionId ?? "—"}
                </TableCell>
                <TableCell className={CELL}>{attemptTarget(execution) ?? "local"}</TableCell>
                <TableCell className={cn(CELL, "tabular-nums")}>
                  {clockOf(execution.startedAt ?? execution.createdAt) ?? "—"}
                </TableCell>
                <TableCell className={cn(CELL, "tabular-nums")}>
                  {seconds === null ? "—" : formatSpan(seconds)}
                </TableCell>
                <TableCell className={cn(CELL, "text-muted-foreground")}>
                  {attemptTasksText(journals[index])}
                </TableCell>
                <TableCell className={CELL} />
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {selected ? (
        <div className="space-y-8 px-6 pt-8 pb-6">
          {headline ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-hairline bg-status-failed-soft px-3 py-2"
            >
              <StatusIcon status={selected.status} className="mt-px size-icon-sm shrink-0" />
              <span className="min-w-0 break-words text-label text-foreground">
                <span className="font-mono">{headline}</span>
                {recovery ? (
                  <span className="mt-1 block text-muted-foreground">{recovery}</span>
                ) : null}
              </span>
            </p>
          ) : null}

          <TaskProductList
            products={products}
            activePath={pinnedPath}
            onOpen={(path) => setPinned({ executionId: selected.executionId, path })}
          />

          <section aria-label="Files" className="flex h-[28rem] min-h-0 flex-col">
            <SectionHead title={`Files of ${selected.executionId}`} />
            <div className="min-h-0 flex-1 pt-3">
              <RunExecutionOutputs
                fill
                assetGroupLabel="Registered by this attempt"
                preferred={pinnedPath ? { kind: "file", path: pinnedPath } : failureSelection}
                outputs={outputs}
                error={logsError}
                projectId={run.projectId}
                experimentId={run.experimentId}
                runId={run.id}
                selectedExecutionId={selected.executionId}
              />
            </div>
          </section>

          <section
            aria-label="Workflow"
            className={cn("flex shrink-0 flex-col", graph ? "h-64" : "min-h-0")}
          >
            <header className="flex items-center gap-2 border-b border-border pb-1">
              <h3 className="text-body text-foreground">Workflow</h3>
              {workflow && onOpenWorkflow ? (
                <button
                  type="button"
                  onClick={onOpenWorkflow}
                  className="ml-auto text-label text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  Open definition
                </button>
              ) : null}
            </header>
            <div className={cn("min-h-0 pt-3", graph && "flex-1")}>
              {graph ? (
                <WorkflowGraph
                  ir={graph}
                  height="100%"
                  className="h-full"
                  onNodeClick={(taskId) => onInspectTask(taskId, run.id)}
                />
              ) : graphError ? (
                <WorkbenchOperationState
                  kind="error"
                  density="compact"
                  title="Could not load workflow"
                  detail={graphError}
                />
              ) : graphLoading ? (
                <WorkbenchOperationState
                  kind="loading"
                  density="compact"
                  title="Loading workflow…"
                  skeletonRows={3}
                />
              ) : (
                <p className="text-label text-muted-foreground">No workflow snapshot.</p>
              )}
            </div>
          </section>

          {columns.length > 0 && row ? (
            <section aria-label="Executor" className="space-y-2">
              <SectionHead title="Executor" />
              <PropertyList
                entries={columns.map((column) => {
                  const Cell = column.Cell;
                  return { label: column.header, value: <Cell execution={row} /> };
                })}
              />
            </section>
          ) : null}
          {row
            ? details.map((detail) => {
                const Detail = detail.Component;
                return (
                  <section key={detail.id} aria-label={detail.title} className="space-y-2">
                    <SectionHead title={detail.title} />
                    <Detail execution={row} runId={run.id} />
                  </section>
                );
              })
            : null}
        </div>
      ) : null}
    </div>
  );
};
