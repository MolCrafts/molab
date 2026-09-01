import { Eye } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { RunStatusBadge, WorkbenchIconAction } from "@/components/workbench";
import { formatDuration, formatRelative, formatTimestamp } from "@/lib/format-time";

import { RunsRecentEvents } from "../RunsRecentEvents";
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
  const end = run.finishedAt ? new Date(run.finishedAt).getTime() : Date.now();
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

  return (
    <div className="flex flex-col">
      <Section title="Backend">
        <Field label="Backend" value={run.backend ?? "—"} />
        <Field label="Cluster" value={run.cluster ?? "—"} />
        <Field label="Scheduler" value={run.scheduler ?? "—"} />
        <Field label="Profile" value={run.profile ?? "—"} />
        {run.latestSchedulerJobId && (
          <Field label="Scheduler job" value={run.latestSchedulerJobId} mono />
        )}
      </Section>

      <Section title="Lifecycle">
        <Field label="Submitted" value={formatTimestamp(run.createdAt)} />
        <Field
          label="Started"
          value={run.executions[0]?.startedAt ? formatTimestamp(run.executions[0].startedAt) : "—"}
        />
        <Field label="Finished" value={formatTimestamp(run.finishedAt)} />
        <Field label="Duration" value={formatDuration(duration)} />
        <Field label="Executions" value={String(run.executionCount)} />
      </Section>

      <Section title={`Recent events (${Math.min(8, 1 + 2 * run.executions.length)})`}>
        <RunsRecentEvents run={run} />
      </Section>

      {run.executions.length > 0 && (
        <Section title={`Attempts (${run.executions.length})`}>
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
        <span className="text-muted-foreground">{formatRelative(execution.startedAt)}</span>
      </div>
    </div>
    <WorkbenchIconAction
      label={selected ? "Clear selected attempt" : `Inspect attempt ${execution.executionId}`}
      onClick={onSelect}
      aria-pressed={selected}
      className={selected ? "bg-interactive" : undefined}
    >
      <Eye className="size-3.5" />
    </WorkbenchIconAction>
  </li>
);
