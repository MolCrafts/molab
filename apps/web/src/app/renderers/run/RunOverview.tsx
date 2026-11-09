/**
 * Run Overview (Figma L04-1…L04-4): level 2 is one verdict line — the status
 * word in its colour, what it is about, the elapsed time; level 3 is one line
 * of evidence that expands in place to the error and "Open in Logs at line N".
 * Then the attempt's tasks on a clock and one comparison chart: this run among
 * its siblings on the swept axis. A success adds what it registered. No
 * tallies, no cards. Everything reads the attempt the page shows.
 */

import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  LoaderCircle,
  Terminal,
} from "lucide-react";
import {
  type ComponentType,
  type JSX,
  type ReactNode,
  type SVGProps,
  useMemo,
  useState,
} from "react";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import { StatusIcon, SweepChart } from "@/app/components/entity";
import { type ComparedRun, keyMetric, sweepOf } from "@/app/renderers/run/runCompare";
import {
  clockWindow,
  errorLine,
  resultFigures,
  runVerdict,
  taskClock,
} from "@/app/renderers/run/runStory";
import { TaskClock } from "@/app/renderers/run/TaskClock";
import { useRunSiblings } from "@/app/renderers/run/useRunSiblings";
import { runLabel } from "@/app/runs/runTitle";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import { useExecutionLog } from "@/app/state/executionLog";
import { isActiveStatus, STATUS } from "@/app/status/vocabulary";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import { formatBytes } from "@/lib/format-bytes";
import { cn } from "@/lib/utils";
import { entityCitationsQueryOptions } from "@/plugins/knowledge/queries";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";

/** A run view a file opens in: a plugin's tab, or Logs. */
export interface OpenInView {
  value: string;
  label: string;
  Icon?: ComponentType<SVGProps<SVGSVGElement>>;
}

export interface RunOverviewProps {
  run: RunSummary;
  /** The attempt the page shows; null when the run has none. */
  attempt: ExecutionRecordSummary | null;
  /** That attempt's outputs (results, registered files, evidence). */
  outputs: ExecutionOutputsResponse | null;
  /** The view a file of this attempt opens in, if any claims it. */
  openIn?: (file: { name: string; relPath: string }) => OpenInView | null;
  onOpenView?: (view: string, focus?: { line?: number }) => void;
  onPreviewTask?: (taskId: string) => void;
  onPreviewRun?: (runId: string) => void;
  onPreviewAsset?: (assetId: string) => void;
  onOpenKnowledge?: (path: string) => void;
}

/** A section: its name, the one readout it exists for, then the body. No hairline, no box. */
const Section = ({
  title,
  readout,
  children,
}: {
  title: string;
  readout?: ReactNode;
  children: ReactNode;
}): JSX.Element => (
  <section aria-label={title} className="min-w-0 space-y-3">
    <header className="flex min-w-0 items-baseline gap-3">
      <h2 className="min-w-0 truncate text-body text-foreground">{title}</h2>
      {readout ? (
        <span className="ml-auto shrink-0 font-mono text-label text-muted-foreground">
          {readout}
        </span>
      ) : null}
    </header>
    {children}
  </section>
);

const Pending = ({ label }: { label: string }): JSX.Element => (
  <span role="status" aria-label={label}>
    <LoaderCircle
      aria-hidden
      className="mol-motion-progress-spin size-icon text-muted-foreground"
    />
  </span>
);

/** Level 2 and 3: the verdict line and its one line of evidence. */
const Verdict = ({
  run,
  attempt,
  verdict,
  onOpenView,
}: {
  run: RunSummary;
  attempt: ExecutionRecordSummary;
  verdict: ReturnType<typeof runVerdict>;
  onOpenView?: RunOverviewProps["onOpenView"];
}): JSX.Element => {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(verdict.error);
  // The run log is read only once the evidence is opened, to find the error's line.
  const log = useExecutionLog(run.projectId, run.experimentId, run.id, attempt.executionId, "run", {
    live: false,
    enabled: open && expandable,
  });
  const line = open ? errorLine(log.data?.text, verdict.error) : null;
  const tone = verdict.status === "none" ? null : STATUS[verdict.status].tone;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section aria-label={verdict.headline} className="min-w-0 space-y-1">
      <div className="flex min-w-0 items-center gap-2">
        {verdict.status !== "none" ? (
          <StatusIcon status={verdict.status} className="size-icon shrink-0" />
        ) : null}
        <h2 className="min-w-0 truncate text-title font-semibold">
          {/* Icon OR text (retrofit R3): the glyph is the status; the label what it is about. */}
          <span className="font-semibold text-foreground">
            {verdict.label ?? (verdict.status === "none" ? verdict.word : "")}
          </span>
        </h2>
        {verdict.elapsed ? (
          <span className="ml-auto shrink-0 text-body tabular-nums text-foreground">
            {verdict.elapsed}
          </span>
        ) : null}
      </div>
      {verdict.evidence ? (
        expandable ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
            className="ml-6 flex max-w-full items-center gap-1 rounded-hairline text-left text-body text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <span className="min-w-0 truncate">{verdict.evidence}</span>
            <Chevron aria-hidden className="size-icon-sm shrink-0" />
          </button>
        ) : (
          <p className="ml-6 truncate text-body text-muted-foreground">{verdict.evidence}</p>
        )
      ) : null}
      {open && verdict.error ? (
        <div
          className={cn(
            "mt-3 ml-6 space-y-2 rounded-hairline px-3 py-2",
            tone === "warning" ? "bg-status-warning-soft" : "bg-status-failed-soft",
          )}
        >
          <p className="flex items-start gap-2 font-mono text-label text-foreground">
            <StatusIcon
              status={verdict.status === "none" ? "failed" : verdict.status}
              className="mt-px size-icon-sm shrink-0"
            />
            <span className="min-w-0 whitespace-pre-wrap break-words">{verdict.error}</span>
          </p>
          {onOpenView ? (
            <button
              type="button"
              onClick={() => onOpenView("logs", line ? { line } : undefined)}
              className="ml-6 flex items-center gap-1 text-label text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <Terminal aria-hidden className="size-icon-sm" />
              {line ? `Open in Logs at line ${line}` : "Open in Logs"}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
};

interface OutputRow {
  key: string;
  name: string;
  meta: string;
  assetId: string | null;
  view: OpenInView | null;
}

const basename = (path: string): string => path.split("/").filter(Boolean).pop() ?? path;

/** What a success registered and the evidence it left, each with where it opens. */
const outputRows = (
  outputs: ExecutionOutputsResponse | null,
  openIn: RunOverviewProps["openIn"],
): OutputRow[] => {
  const viewOf = (path: string): OpenInView | null =>
    /(^|\/)(run|stdout|stderr)\.log$/.test(path)
      ? { value: "logs", label: "Logs", Icon: Terminal }
      : (openIn?.({ name: basename(path), relPath: path }) ?? null);
  return [
    ...(outputs?.assets ?? []).map((asset) => ({
      key: `asset:${asset.id}`,
      name: basename(asset.file) || asset.title,
      meta: [asset.mediaType, formatBytes(asset.size)].filter(Boolean).join(" · "),
      assetId: asset.id,
      view: viewOf(asset.file),
    })),
    // Records (execution.json, workflow.json) are molab's bookkeeping, not what the run produced.
    ...(outputs?.evidence ?? [])
      .filter((item) => item.kind !== "record")
      .map((item) => ({
        key: `evidence:${item.path}`,
        name: basename(item.path),
        meta: [item.kind, formatBytes(item.size)].filter(Boolean).join(" · "),
        assetId: null,
        view: viewOf(item.path),
      })),
  ];
};

const Outputs = ({
  rows,
  onPreviewAsset,
  onOpenView,
}: {
  rows: readonly OutputRow[];
  onPreviewAsset?: (assetId: string) => void;
  onOpenView?: RunOverviewProps["onOpenView"];
}): JSX.Element => (
  <ul className="max-w-[72rem] divide-y divide-border border-b border-border">
    {rows.map((row) => {
      const Icon = row.view?.Icon;
      return (
        <li key={row.key} className="flex h-7 min-w-0 items-center gap-3 text-body">
          <FileText aria-hidden className="size-icon-sm shrink-0 text-muted-foreground" />
          {row.assetId && onPreviewAsset ? (
            <button
              type="button"
              onClick={() => row.assetId && onPreviewAsset(row.assetId)}
              className="w-64 min-w-0 truncate text-left font-mono text-foreground hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {row.name}
            </button>
          ) : (
            <span className="w-64 min-w-0 truncate font-mono text-foreground">{row.name}</span>
          )}
          <span className="min-w-0 flex-1 truncate text-label text-muted-foreground">
            {row.meta}
          </span>
          {row.view && onOpenView ? (
            <button
              type="button"
              onClick={() => row.view && onOpenView(row.view.value)}
              className="flex shrink-0 items-center gap-1 text-label text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {Icon ? <Icon aria-hidden className="size-icon-sm" /> : null}
              {row.view.label}
            </button>
          ) : null}
        </li>
      );
    })}
  </ul>
);

/** This run among its siblings, on the experiment's swept axis, by its key result. */
const Siblings = ({
  run,
  results,
  onPreviewRun,
}: {
  run: RunSummary;
  results: Record<string, unknown> | undefined;
  onPreviewRun?: (runId: string) => void;
}): JSX.Element | null => {
  const { siblings, loading } = useRunSiblings(run, { results: true });
  const sweep = useMemo(() => {
    const self: ComparedRun = {
      id: run.id,
      title: runLabel(run),
      parameters: run.parameters ?? {},
      status: run.executionHistory.at(-1)?.status ?? "pending",
      results: results ?? siblings.find((sibling) => sibling.id === run.id)?.results ?? null,
    };
    const others = siblings.filter((sibling) => sibling.id !== run.id);
    return sweepOf(self, others, keyMetric(self, others));
  }, [run, results, siblings]);
  if (!sweep) return loading ? <Pending label="Reading the sibling runs" /> : null;
  return (
    <Section
      title={`${sweep.metric} across ${sweep.axisKey}`}
      readout={`from ${sweep.siblingsWithResult} sibling ${sweep.siblingsWithResult === 1 ? "run" : "runs"}`}
    >
      <div className="max-w-[44rem]">
        <SweepChart
          points={sweep.points}
          selfSeries={sweep.selfSeries}
          label={`This run's ${sweep.metric} among its siblings across ${sweep.axisKey}`}
          onPick={onPreviewRun}
        />
      </div>
    </Section>
  );
};

const CitedBy = ({
  run,
  onOpenKnowledge,
}: {
  run: RunSummary;
  onOpenKnowledge?: (path: string) => void;
}): JSX.Element | null => {
  const citations = useQuery(
    entityCitationsQueryOptions("run", run.projectId, run.experimentId, run.id),
  );
  const rows = citations.data ?? [];
  if (rows.length === 0) return null;
  return (
    <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-label text-muted-foreground">
      <BookOpen aria-hidden className="size-icon-sm shrink-0" />
      Cited by
      {rows.map((row, index) => (
        <span key={row.path} className="flex items-center gap-2">
          <button
            type="button"
            title={`${row.role} · ${row.path}`}
            onClick={() => onOpenKnowledge?.(row.path)}
            className="text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {row.title}
          </button>
          {index < rows.length - 1 ? <span aria-hidden>·</span> : null}
        </span>
      ))}
    </p>
  );
};

export const RunOverview = ({
  run,
  attempt,
  outputs,
  openIn,
  onOpenView,
  onPreviewTask,
  onPreviewRun,
  onPreviewAsset,
  onOpenKnowledge,
}: RunOverviewProps): JSX.Element => {
  const history = run.executionHistory;
  const journal = useQuery({
    ...executionJournalQueryOptions(
      run.projectId,
      run.experimentId,
      run.id,
      attempt?.executionId ?? "",
    ),
    enabled: attempt !== null,
    refetchInterval: journalRefetchInterval(attempt?.status),
  });
  // Before an attempt journals anything (queued), its tasks are the workflow's, all waiting.
  const graph = useMemo(() => {
    const journalled = journal.data ? normalizeTaskGraph(journal.data) : null;
    if (journalled && journalled.task_configs.length > 0) return journalled;
    if (!attempt || !isActiveStatus(attempt.status)) return journalled;
    try {
      const definition = run.workflowSource
        ? normalizeTaskGraph(JSON.parse(run.workflowSource))
        : null;
      return definition && definition.task_configs.length > 0
        ? {
            ...definition,
            task_configs: definition.task_configs.map(
              ({ status: _s, startedAt: _a, finishedAt: _b, ...task }) => task,
            ),
          }
        : journalled;
    } catch {
      return journalled;
    }
  }, [journal.data, run.workflowSource, attempt]);
  const now = useMemo(() => Date.now(), []);
  const results = outputs?.results as Record<string, unknown> | undefined;
  const figures = useMemo(() => resultFigures(results), [results]);
  const scoped = useMemo(
    () => ({
      ...run,
      executionHistory: attempt ? history.slice(0, history.indexOf(attempt) + 1) : [],
    }),
    [run, history, attempt],
  );
  const verdict = runVerdict(scoped, graph, now, figures);
  const rows = useMemo(() => taskClock(graph, attempt, now), [graph, attempt, now]);
  const succeeded = verdict.status === "succeeded";
  const outputsList = succeeded ? outputRows(outputs, openIn) : [];

  return (
    <div className="h-full min-h-0 overflow-auto bg-background">
      <div className="space-y-8 px-6 py-6">
        {attempt ? (
          <Verdict run={run} attempt={attempt} verdict={verdict} onOpenView={onOpenView} />
        ) : (
          <section aria-label="Not run yet" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusIcon status="pending" className="size-icon shrink-0" />
              <h2 className="text-title font-semibold text-muted-foreground">Not started</h2>
            </div>
            <p className="ml-6 text-body text-muted-foreground">
              No attempt yet. Start it from the editor actions.
            </p>
          </section>
        )}

        {attempt ? (
          <Section title="Tasks" readout={clockWindow(rows)}>
            {journal.isPending ? (
              <Pending label="Reading the attempt's journal" />
            ) : rows.length > 0 ? (
              <TaskClock rows={rows} onPreviewTask={onPreviewTask} />
            ) : (
              <p className="text-body text-muted-foreground">This attempt journalled no tasks.</p>
            )}
          </Section>
        ) : null}

        <Siblings run={run} results={results} onPreviewRun={onPreviewRun} />

        {outputsList.length > 0 ? (
          <Section title="Outputs">
            <Outputs rows={outputsList} onPreviewAsset={onPreviewAsset} onOpenView={onOpenView} />
          </Section>
        ) : null}

        <CitedBy run={run} onOpenKnowledge={onOpenKnowledge} />
      </div>
    </div>
  );
};
