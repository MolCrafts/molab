import { Eye } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { RunStatusBadge, WorkbenchIconAction } from "@/components/workbench";
import { formatDuration, formatRelative, formatTimestamp } from "@/lib/format-time";

import { RunsRecentEvents } from "../RunsRecentEvents";
import { runFinishedAt, runStartedAt } from "../projections";
import type { WorkspaceExecutionRow, WorkspaceRunRow } from "../types";

interface RunInspectorDetailsProps {
  run: WorkspaceRunRow;
  selectedExecutionId: string | null;
  onSelectExecution: (id: string | null) => void;
}

const computeRunDuration = (run: WorkspaceRunRow): number | null => {
  const start = run.executions
    .map((exec) => (exec.startedAt ? new Date(exec.startedAt).getTime() : NaN))
    .filter((v) => !Number.isNaN(v))
    .sort((a, b) => a - b)[0];
  if (typeof start !== "number") return null;
  const finishedAt = run.statusSummary.active > 0 ? null : runFinishedAt(run);
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
};

export const RunInspectorDetails = ({
  run,
  selectedExecutionId,
  onSelectExecution,
}: RunInspectorDetailsProps): JSX.Element => {
  const parameterEntries = Object.entries(run.parameters);
  const duration = computeRunDuration(run);
  const selectedExecution = run.executions.find(
    (execution) => execution.executionId === selectedExecutionId,
  );

  return (
    <div className="flex flex-col">
      <Section title="Run definition">
        <Field label="Definition" value={run.definitionHash} mono />
        <Field label="Experiment revision" value={run.experimentRevisionId} mono />
        <Field label="Target hint" value={run.targetHint ?? "—"} />
        <Field label="Input assets" value={String(run.inputAssetIds.length)} />
      </Section>

      <Section title="Execution summary">
        <Field label="Run created" value={formatTimestamp(run.createdAt)} />
        <Field label="First started" value={formatTimestamp(runStartedAt(run))} />
        <Field label="Last finished" value={formatTimestamp(runFinishedAt(run))} />
        <Field label="Duration" value={formatDuration(duration)} />
        <Field label="Executions" value={String(run.statusSummary.total)} />
        <Field label="Active" value={String(run.statusSummary.active)} />
      </Section>

      {selectedExecution && (
        <Section title="Selected execution">
          <Field label="Mode" value={selectedExecution.mode} />
          <Field label="Backend" value={selectedExecution.backend ?? "—"} />
          <Field label="Cluster" value={selectedExecution.backendMetadata.cluster_name ?? "—"} />
          <Field label="Scheduler" value={selectedExecution.backendMetadata.scheduler ?? "—"} />
          <Field label="Profile" value={selectedExecution.backendMetadata.profile ?? "—"} />
          <Field label="Scheduler job" value={selectedExecution.schedulerJobId ?? "—"} mono />
        </Section>
      )}

      <Section title={`Recent events (${Math.min(8, 1 + 2 * run.executions.length)})`}>
        <RunsRecentEvents run={run} />
      </Section>

      {run.executions.length > 0 && (
        <Section title={`Executions (${run.executions.length})`}>
          <ul className="space-y-1">
            {run.executions.map((execution) => (
              <ExecutionRow
                key={execution.executionId}
                execution={execution}
                selected={execution.executionId === selectedExecutionId}
                onSelect={() =>
                  onSelectExecution(
                    execution.executionId === selectedExecutionId ? null : execution.executionId,
                  )
                }
              />
            ))}
          </ul>
        </Section>
      )}

      {parameterEntries.length > 0 && (
        <Section title="Parameters">
          {parameterEntries.map(([key, value]) => (
            <Field key={key} label={key} value={String(value)} mono />
          ))}
        </Section>
      )}
    </div>
  );
};

const Section = ({ title, children }: { title: string; children: ReactNode }): JSX.Element => (
  <section className="border-b border-border/60 px-4 py-3">
    <h3 className="mb-3 text-label font-medium text-muted-foreground">{title}</h3>
    <div className="space-y-2 text-label">{children}</div>
  </section>
);

const Field = ({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}): JSX.Element => (
  <div className="flex items-baseline justify-between gap-3">
    <span className="text-muted-foreground">{label}</span>
    <span
      className={
        mono ? "max-w-3/5 truncate font-mono text-foreground" : "max-w-3/5 truncate text-foreground"
      }
      title={value}
    >
      {value}
    </span>
  </div>
);

interface ExecutionRowProps {
  execution: WorkspaceExecutionRow;
  selected: boolean;
  onSelect: () => void;
}

const ExecutionRow = ({ execution, selected, onSelect }: ExecutionRowProps): JSX.Element => (
  <li
    className={
      selected
        ? "flex items-center gap-2 border-l-2 border-accent bg-accent-muted px-2 py-1.5 text-label"
        : "flex items-center gap-2 border-l-2 border-transparent px-2 py-1.5 text-label"
    }
  >
    <div className="min-w-0 flex-1">
      <span className="truncate font-mono text-muted-foreground" title={execution.executionId}>
        {execution.executionId.slice(0, 14)}
      </span>
      <div className="mt-1 flex items-center gap-2">
        <RunStatusBadge status={execution.status} size="sm" />
        <span className="text-muted-foreground">
          {formatRelative(execution.startedAt ?? execution.createdAt)}
        </span>
      </div>
    </div>
    <WorkbenchIconAction
      label={selected ? "Clear selected execution" : `Inspect execution ${execution.executionId}`}
      onClick={onSelect}
      aria-pressed={selected}
      className={selected ? "bg-interactive" : undefined}
    >
      <Eye className="size-3.5" />
    </WorkbenchIconAction>
  </li>
);
