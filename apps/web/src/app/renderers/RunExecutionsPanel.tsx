import { AlertTriangle, Network } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { runsApi } from "@/api";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import {
  CopyButton,
  EmptyState,
  InventoryCanvas,
  OverviewSurface,
  StatusIcon,
  statusKey,
} from "@/app/components/entity";
import { listExecutionColumns, listExecutionDetails } from "@/app/registry";
import { formatDuration } from "@/app/renderers/dashboardData";
import { RunExecutionOutputs } from "@/app/renderers/run/RunExecutionOutputs";
import type { ExecutionRecordSummary, RunSummary, WorkflowSummary } from "@/app/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RunStatusBadge, WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";
import { normalizeTaskGraph } from "@/components/workflow/flowgram-document";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";
import { WorkflowGraph } from "@/components/workflow/workflow-graph";
import type { ExecutionRowData } from "@/lib/contribution-types";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";

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

interface RunExecutionsPanelProps {
  run: RunSummary;
  workflow?: WorkflowSummary;
  selectedExecutionId: string | null;
  onSelectExecution: (executionId: string) => void;
  onInspectTask: (taskId: string, runId: string) => void;
  onOpenWorkflow?: () => void;
  outputs: ExecutionOutputsResponse | null;
  logsError: string | null;
  onPromoted?: () => void;
}

export const RunExecutionsPanel = ({
  run,
  workflow,
  selectedExecutionId,
  onSelectExecution,
  onInspectTask,
  onOpenWorkflow,
  outputs,
  logsError,
  onPromoted,
}: RunExecutionsPanelProps): JSX.Element => {
  const history = run.executionHistory;
  const selected = history.find((item) => item.executionId === selectedExecutionId) ?? null;
  const selectedIndex = selected
    ? history.findIndex((item) => item.executionId === selected.executionId)
    : -1;
  const [graph, setGraph] = useState<TaskGraphJson | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    if (!selectedExecutionId) {
      setGraph(null);
      setGraphError(null);
      return;
    }
    const load = (): void => {
      runsApi
        .getRunExecution(run.projectId, run.experimentId, run.id, selectedExecutionId)
        .then((response) => {
          if (cancelled) return;
          setGraph(response.workflow ? normalizeTaskGraph(response.workflow) : null);
          setGraphError(null);
        })
        .catch((reason: unknown) => {
          if (!cancelled)
            setGraphError(
              reason instanceof Error ? reason.message : "Failed to load execution workflow",
            );
        });
    };
    load();
    if (selected?.status === "queued" || selected?.status === "running")
      interval = setInterval(load, 1500);
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [run.experimentId, run.id, run.projectId, selected?.status, selectedExecutionId]);

  const failedTasks =
    graph?.task_configs.filter((task) => statusKey(task.status) === "failed") ?? [];
  const row = selected ? executionRow(selected, run.id) : null;
  const columns = useMemo(() => listExecutionColumns(row?.backend), [row?.backend]);
  const details = useMemo(() => listExecutionDetails(row?.backend), [row?.backend]);

  if (history.length === 0) {
    return (
      <OverviewSurface>
        <InventoryCanvas>
          <EmptyState
            title="No executions"
            description="Create an execution to realize this Run definition."
          />
        </InventoryCanvas>
      </OverviewSurface>
    );
  }

  return (
    <OverviewSurface>
      <InventoryCanvas className="max-w-6xl space-y-8">
        <section className="space-y-3">
          <h3 className="text-body-lg font-medium text-foreground">
            Executions
            <span className="ml-2 font-mono text-micro font-normal text-muted-foreground">
              {history.length}
            </span>
          </h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-14">#</TableHead>
                <TableHead className="w-24">State</TableHead>
                <TableHead>Execution</TableHead>
                <TableHead className="w-24">Mode</TableHead>
                <TableHead className="w-40">Started</TableHead>
                <TableHead className="w-28">Duration</TableHead>
                <TableHead className="w-32">Backend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((execution, index) => {
                const active = execution.executionId === selectedExecutionId;
                return (
                  <TableRow
                    key={execution.executionId}
                    className={cn("cursor-pointer", active && "bg-muted/40")}
                    onClick={() => onSelectExecution(execution.executionId)}
                    data-state={active ? "selected" : undefined}
                  >
                    <TableCell className="font-mono text-label text-muted-foreground">
                      <span className="inline-flex items-center gap-2">
                        <StatusIcon status={execution.status} />
                        {index + 1}
                      </span>
                    </TableCell>
                    <TableCell>
                      <RunStatusBadge status={execution.status} size="sm" />
                    </TableCell>
                    <TableCell className="font-mono text-label">{execution.executionId}</TableCell>
                    <TableCell className="text-label text-muted-foreground">
                      {execution.mode}
                    </TableCell>
                    <TableCell className="text-label text-muted-foreground">
                      {formatDateTime(execution.startedAt ?? execution.createdAt)}
                    </TableCell>
                    <TableCell className="font-mono text-label text-muted-foreground">
                      {formatDuration(execution.startedAt, execution.finishedAt) ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-label text-muted-foreground">
                      {backendOf(execution)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </section>

        {!selected ? (
          <section className="border-t border-border py-10">
            <EmptyState
              title="Select an execution"
              description="Execution details, outputs, environment, and plugin tools require an explicit physical attempt."
            />
          </section>
        ) : (
          <>
            <section className="space-y-3">
              <div className="flex items-baseline justify-between gap-2">
                <h3 className="text-body-lg font-medium text-foreground">
                  Execution #{selectedIndex + 1}
                </h3>
                <div className="flex items-center gap-1">
                  <CopyButton value={selected.executionId} label="execution ID" />
                  {workflow && onOpenWorkflow && (
                    <WorkbenchIconAction label="Open workflow definition" onClick={onOpenWorkflow}>
                      <Network className="h-3.5 w-3.5" />
                    </WorkbenchIconAction>
                  )}
                </div>
              </div>
              <Table>
                <TableBody>
                  <TableRow>
                    <TableCell className="w-40 text-label text-muted-foreground">State</TableCell>
                    <TableCell>
                      <RunStatusBadge status={selected.status} size="sm" />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-label text-muted-foreground">Mode</TableCell>
                    <TableCell className="font-mono text-label">{selected.mode}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-label text-muted-foreground">Created</TableCell>
                    <TableCell className="font-mono text-label">
                      {formatDateTime(selected.createdAt)}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-label text-muted-foreground">Start</TableCell>
                    <TableCell className="font-mono text-label">
                      {selected.startedAt ? formatDateTime(selected.startedAt) : "—"}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-label text-muted-foreground">End</TableCell>
                    <TableCell className="font-mono text-label">
                      {selected.finishedAt ? formatDateTime(selected.finishedAt) : "—"}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-label text-muted-foreground">Backend</TableCell>
                    <TableCell className="font-mono text-label">{backendOf(selected)}</TableCell>
                  </TableRow>
                  {selected.basedOnExecutionId && (
                    <TableRow>
                      <TableCell className="text-label text-muted-foreground">Based on</TableCell>
                      <TableCell className="font-mono text-label">
                        {selected.basedOnExecutionId}
                      </TableCell>
                    </TableRow>
                  )}
                  {selected.checkpointArtifactId && (
                    <TableRow>
                      <TableCell className="text-label text-muted-foreground">Checkpoint</TableCell>
                      <TableCell className="font-mono text-label">
                        {selected.checkpointArtifactId}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </section>

            {row && columns.length > 0 && (
              <section className="space-y-3">
                <h3 className="text-body-lg font-medium text-foreground">Executor</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      {columns.map((column) => (
                        <TableHead key={column.id}>{column.header}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      {columns.map((column) => {
                        const Cell = column.Cell;
                        return (
                          <TableCell key={column.id}>
                            <Cell execution={row} />
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  </TableBody>
                </Table>
              </section>
            )}

            {row &&
              details.map((detail) => {
                const Detail = detail.Component;
                return (
                  <section key={detail.id} className="space-y-3">
                    <h3 className="text-body-lg font-medium text-foreground">{detail.title}</h3>
                    <Detail execution={row} runId={run.id} />
                  </section>
                );
              })}

            <section className="space-y-3">
              <h3 className="text-body-lg font-medium text-foreground">Outputs</h3>
              <RunExecutionOutputs
                outputs={outputs}
                error={logsError}
                projectId={run.projectId}
                experimentId={run.experimentId}
                runId={run.id}
                selectedExecutionId={selectedExecutionId}
                onPromoted={onPromoted}
              />
            </section>

            <section className="space-y-3">
              <h3 className="text-body-lg font-medium text-foreground">Observed workflow</h3>
              {failedTasks.length > 0 && (
                <div className="border-y border-status-failed/25 bg-status-failed-soft px-3 py-3 text-label text-status-failed-foreground">
                  <div className="flex flex-wrap items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Failed at
                    {failedTasks.map((task) => (
                      <WorkbenchAction
                        key={task.id}
                        kind="ghost"
                        size="content"
                        className="font-mono underline-offset-2 hover:underline"
                        onClick={() => onInspectTask(task.id, run.id)}
                      >
                        {task.id}
                      </WorkbenchAction>
                    ))}
                  </div>
                </div>
              )}
              {graph ? (
                <div className="overflow-hidden border border-border bg-canvas">
                  <WorkflowGraph
                    ir={graph}
                    height={420}
                    onNodeClick={(taskId) => onInspectTask(taskId, run.id)}
                  />
                </div>
              ) : (
                <p className="py-6 text-label text-muted-foreground">
                  No observed workflow snapshot for this execution.
                </p>
              )}
              {graphError && <p className="text-label text-destructive">{graphError}</p>}
            </section>
          </>
        )}
      </InventoryCanvas>
    </OverviewSurface>
  );
};
