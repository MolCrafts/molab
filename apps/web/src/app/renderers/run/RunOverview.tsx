import { useQuery } from "@tanstack/react-query";
import {
  CircleDashed,
  Equal,
  FileText,
  History,
  ListChecks,
  LoaderCircle,
  RotateCcw,
  SlidersHorizontal,
  Timer,
} from "lucide-react";
import { type JSX, type ReactNode, useMemo } from "react";

import {
  EmptyState,
  formatSpan,
  GaugeSection,
  InventoryCanvas,
  OverviewCanvas,
  OverviewSurface,
  PositionChart,
  STATUS_INK,
  StatusIcon,
  Tally,
  TimelineChart,
  type TimelineSpan,
} from "@/app/components/entity";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { formatScalar } from "@/app/renderers/dashboardData";
import {
  distinguishingParameters,
  resultFigures,
  runVerdict,
  siblingStanding,
  taskSpans,
  unstartedTasks,
} from "@/app/renderers/run/runStory";
import { groupForStatus, STATUS_GROUPS } from "@/app/runs/statusGroups";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { KnowledgeBacklinksCard } from "@/plugins/knowledge/KnowledgeBacklinksCard";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";

/** The run's parameter list. Overview does not host it. */
export const RunParameters = ({ parameters }: { parameters: [string, unknown][] }): JSX.Element => (
  <OverviewSurface>
    <InventoryCanvas>
      <PropertyGrid entries={parameters} />
    </InventoryCanvas>
  </OverviewSurface>
);

/**
 * One object's fields, as a property list. A two-column `<Table>` with a header
 * row is table chrome around what is really a definition list.
 */
const PropertyGrid = ({ entries }: { entries: [string, unknown][] }): JSX.Element => {
  if (entries.length === 0) {
    return <p className="text-label text-muted-foreground">No parameters</p>;
  }
  return (
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
      {entries.map(([key, rawValue]) => {
        const value = formatScalar(rawValue);
        return (
          <div key={key} className="contents">
            <dt className="min-w-0 truncate font-mono text-label text-muted-foreground">{key}</dt>
            <dd className="min-w-0 break-all font-mono text-body text-foreground" title={value}>
              {value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
};

const time = (value: string | null | undefined): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

/** "#2 · resume" — attempts are named by order and mode; the id lives on the Executions tab. */
const attemptName = (execution: ExecutionRecordSummary, index: number): string =>
  `#${index + 1} · ${execution.mode}`;

const attemptSpans = (history: readonly ExecutionRecordSummary[], now: number): TimelineSpan[] =>
  history.flatMap((execution, index) => {
    const start = time(execution.startedAt ?? execution.createdAt);
    if (start === null) return [];
    const status = groupForStatus(execution.status) ?? "pending";
    const active = status === "running" || status === "pending";
    const seconds = Math.max(0, (time(execution.finishedAt) ?? now) - start) / 1000;
    const word = STATUS_GROUPS.find((group) => group.id === status)?.label ?? status;
    return [
      {
        key: execution.executionId,
        label: attemptName(execution, index),
        start,
        end: active ? null : time(execution.finishedAt),
        status,
        tip: `${attemptName(execution, index)} · ${word} · ${formatSpan(seconds)}`,
      },
    ];
  });

/** The verdict in symbols: status icon, what it is about, how long. The sentence is its name. */
const Verdict = ({
  verdict,
  actions,
}: {
  verdict: ReturnType<typeof runVerdict>;
  actions: ReactNode;
}): JSX.Element => {
  const ink = verdict.status === "none" ? "text-foreground" : STATUS_INK[verdict.status];
  return (
    <section aria-label={verdict.headline} className="min-w-0 space-y-3">
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2" title={verdict.headline}>
        {verdict.status !== "none" ? (
          <StatusIcon
            status={verdict.status}
            label={verdict.headline}
            className="size-7 shrink-0"
          />
        ) : null}
        {verdict.subject ? (
          <h2 className={cn("min-w-0 truncate text-display font-semibold tracking-tight", ink)}>
            {verdict.subject}
          </h2>
        ) : verdict.status === "none" ? (
          <h2 className="text-display font-semibold tracking-tight text-foreground">
            {verdict.headline}
          </h2>
        ) : null}
        {verdict.elapsed ? (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-display font-semibold tabular-nums tracking-tight",
              verdict.subject ? "text-foreground" : ink,
            )}
          >
            <Timer aria-hidden className="size-6 opacity-70" />
            {verdict.elapsed}
          </span>
        ) : null}
        <span className="ml-auto flex shrink-0 items-center gap-1">{actions}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-label text-muted-foreground">
        {verdict.tasks.total > 0 ? (
          <Tally
            icon={ListChecks}
            value={`${verdict.tasks.done}/${verdict.tasks.total}`}
            label={`${verdict.tasks.done} of ${verdict.tasks.total} tasks done`}
          />
        ) : null}
        {verdict.attempt ? (
          <Tally
            icon={RotateCcw}
            value={`#${verdict.attempt.index} ${verdict.attempt.mode}`}
            label={`Attempt ${verdict.attempt.index} of ${verdict.attempt.total}, a ${verdict.attempt.mode}`}
          />
        ) : null}
      </div>
      {verdict.error ? (
        <p
          className="line-clamp-2 max-w-[100ch] break-words font-mono text-label text-foreground"
          title={verdict.error}
        >
          {verdict.error}
        </p>
      ) : null}
    </section>
  );
};

/** Nothing to draw: a dash, its reason on hover. */
const EmptyMark = ({ label }: { label: string }): JSX.Element => (
  <span role="img" aria-label={label} title={label} className="text-title text-muted-foreground">
    —
  </span>
);

/** One run, told: what happened, inside it and against the runs beside it. */
export const RunOverview = ({
  run,
  results,
  onOpenExecution,
  onOpenLogs,
  onOpenParameters,
  onOpenRun,
  onInspectTask,
}: {
  run: RunSummary;
  /** The latest attempt's reported results. */
  results?: Record<string, unknown>;
  onOpenExecution?: (executionId: string) => void;
  onOpenLogs?: () => void;
  onOpenParameters?: () => void;
  /** Open a sibling run. */
  onOpenRun?: (runId: string) => void;
  onInspectTask?: (taskId: string) => void;
}): JSX.Element => {
  const history = run.executionHistory;
  const latest = history[history.length - 1] ?? null;
  const journal = useQuery({
    ...executionJournalQueryOptions(
      run.projectId,
      run.experimentId,
      run.id,
      latest?.executionId ?? "",
    ),
    enabled: latest !== null,
    refetchInterval: journalRefetchInterval(latest?.status),
  });
  const graph = useMemo(
    () => (journal.data ? normalizeTaskGraph(journal.data) : null),
    [journal.data],
  );
  const { rows: siblings } = useScopeRuns({ experimentId: run.experimentId }, true);
  const now = useMemo(() => Date.now(), []);

  const verdict = runVerdict(run, graph, now);
  const tasks = useMemo(() => taskSpans(graph, now), [graph, now]);
  const waiting = unstartedTasks(graph);
  const standing = useMemo(() => siblingStanding(run.id, siblings, now), [run.id, siblings, now]);
  const coordinates = useMemo(
    () => distinguishingParameters(run.parameters ?? {}, siblings),
    [run.parameters, siblings],
  );
  const figures = resultFigures(results);
  const attempts = useMemo(() => attemptSpans(history, now), [history, now]);

  if (!latest) {
    return (
      <OverviewCanvas>
        <EmptyState
          title="Not run yet"
          description="0 attempts. Start this run from the toolbar and its story appears here."
        />
      </OverviewCanvas>
    );
  }

  const actions = (
    <>
      {onOpenLogs ? (
        <WorkbenchAction
          kind="ghost"
          size="compact"
          icon={<FileText aria-hidden />}
          onClick={onOpenLogs}
        >
          Logs
        </WorkbenchAction>
      ) : null}
      {onOpenExecution ? (
        <WorkbenchAction
          kind="ghost"
          size="compact"
          icon={<History aria-hidden />}
          onClick={() => onOpenExecution(latest.executionId)}
        >
          Execution
        </WorkbenchAction>
      ) : null}
    </>
  );

  return (
    <OverviewCanvas>
      <Verdict verdict={verdict} actions={actions} />

      <GaugeSection
        title="Tasks"
        readout={
          waiting > 0 ? (
            <Tally icon={CircleDashed} value={waiting} label={`${waiting} tasks not started`} />
          ) : undefined
        }
      >
        {journal.isPending ? (
          <span role="status" aria-label="Reading the attempt's journal">
            <LoaderCircle
              aria-hidden
              className="mol-motion-progress-spin size-icon text-muted-foreground"
            />
          </span>
        ) : tasks.length > 0 ? (
          <TimelineChart
            spans={tasks}
            label="The latest attempt's tasks, start to finish"
            onPick={onInspectTask}
          />
        ) : (
          <EmptyMark
            label={
              graph && graph.task_configs.length > 0
                ? "No task has started yet"
                : "This attempt journalled no tasks"
            }
          />
        )}
      </GaugeSection>

      <div className="grid min-w-0 gap-x-16 gap-y-12 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <GaugeSection
          title="Siblings"
          readout={
            standing.place ? (
              <Tally
                icon={standing.place === "=" ? Equal : Timer}
                value={standing.place}
                label={standing.rank ?? ""}
              />
            ) : undefined
          }
        >
          {standing.points.length > 1 ? (
            <PositionChart points={standing.points} onPick={onOpenRun} />
          ) : (
            <EmptyMark label="No other finished run in this experiment to compare with" />
          )}
          {coordinates.length > 0 ? (
            <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
              {coordinates.map(({ key, value }) => (
                <div key={key} className="flex min-w-0 items-baseline gap-2">
                  <dt className="font-mono text-label text-muted-foreground">{key}</dt>
                  <dd className="font-mono text-body text-foreground">{value}</dd>
                </div>
              ))}
              {onOpenParameters ? (
                <WorkbenchIconAction label="All parameters" onClick={onOpenParameters}>
                  <SlidersHorizontal aria-hidden />
                </WorkbenchIconAction>
              ) : null}
            </dl>
          ) : null}
        </GaugeSection>

        <GaugeSection title="Results">
          {figures.length > 0 ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
              {figures.slice(0, 6).map(({ key, value }) => (
                <div key={key} className="min-w-0">
                  <dt className="truncate font-mono text-micro text-muted-foreground" title={key}>
                    {key}
                  </dt>
                  <dd
                    className="truncate text-title font-semibold tabular-nums text-foreground"
                    title={value}
                  >
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <EmptyMark
              label={
                verdict.status === "succeeded"
                  ? "This attempt reported no scalar results"
                  : "No results yet"
              }
            />
          )}
        </GaugeSection>
      </div>

      {history.length > 1 ? (
        <GaugeSection
          title="Attempts"
          readout={
            <Tally icon={RotateCcw} value={history.length} label={`${history.length} attempts`} />
          }
        >
          <TimelineChart
            spans={attempts}
            label="This run's attempts, start to finish"
            onPick={onOpenExecution}
          />
        </GaugeSection>
      ) : null}

      <KnowledgeBacklinksCard
        kind="run"
        projectId={run.projectId}
        experimentId={run.experimentId}
        runId={run.id}
      />
    </OverviewCanvas>
  );
};
