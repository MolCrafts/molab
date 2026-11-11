/**
 * Experiment Overview (Figma L03-1, L03-2, L03-8): level 2 is one verdict line
 * — the runs' worst latest status, “1 failed · 1 interrupted of 12 runs”, and
 * what is still active — whose counts open Runs filtered to them; level 3 is
 * one line naming what the runs that need attention share. Then three gauges
 * (Success, In flight, Duration) and two charts: the outcome by a swept
 * parameter (or by task) and the key result on the swept axis. An experiment
 * with no runs says what is missing, in order.
 */

import { type JSX, type ReactNode, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ChoiceToggle,
  DialLegend,
  DurationRange,
  formatSpan,
  GaugeSection,
  Instrument,
  InstrumentStrip,
  MixChart,
  OverviewCanvas,
  quantile,
  StatusGlyphLegend,
  StatusIcon,
  SuccessDial,
  SweepChart,
  UnitMeter,
} from "@/app/components/entity";
import { durationPointsOf, inFlightMarks, useOpenRun } from "@/app/dashboard/dashboardWidgets";
import { varyingParameterKeys } from "@/app/renderers/entityWorkbenchData";
import {
  declaredCellCount,
  type ExperimentVerdict,
  experimentVerdict,
  outcomeByParameter,
} from "@/app/renderers/experiment/experimentStory";
import { useTaskOutcome } from "@/app/renderers/experiment/useTaskOutcome";
import { experimentSweep, keyMetric } from "@/app/renderers/run/runCompare";
import { useRunSiblings } from "@/app/renderers/run/useRunSiblings";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { countStatuses, isActiveStatus } from "@/app/status/vocabulary";
import type { ExperimentSummary, RunSummary } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { cn } from "@/lib/utils";

const TASK_AXIS = "\u0000task";
const RUN_WORDING = { unit: ["run", "runs"] } as const;
const TASK_WORDING = { unit: ["task", "tasks"] } as const;

export interface ExperimentOverviewProps {
  experiment: ExperimentSummary;
  runs: readonly RunSummary[];
  /** The same runs as the workspace inventory has them (attempt rows), for the gauges. */
  rows: readonly WorkspaceRunRow[];
  /** The rows are a truncated page. */
  partial: boolean;
  hasWorkflow: boolean;
  onOpenRuns: (filter?: string) => void;
  onPreviewRun: (runId: string) => void;
  onOpenWorkflow: () => void;
  onNewRun: () => void;
  onSweep: () => void;
}

const LinkText = ({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}): JSX.Element =>
  onClick ? (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-hairline hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        className,
      )}
    >
      {children}
    </button>
  ) : (
    <span className={className}>{children}</span>
  );

/** Level 2 and 3. The counts are links to the Runs they count. Shared with the project (L02). */
export const Verdict = ({
  verdict,
  onOpenRuns,
}: {
  verdict: ExperimentVerdict;
  onOpenRuns: (filter?: string) => void;
}): JSX.Element => {
  // Icon OR text (retrofit R3): the glyph carries the status; the subject says what.
  const quiet = verdict.state === "planned" || verdict.state === "empty";
  return (
    <section aria-label={`${verdict.word} ${verdict.subject}`} className="min-w-0 space-y-1">
      <div className="flex min-w-0 items-center gap-2">
        <StatusIcon status={verdict.status} className="size-icon shrink-0" />
        <h2 className="min-w-0 text-title sm:truncate">
          <LinkText
            className={cn("font-semibold", quiet ? "text-muted-foreground" : "text-foreground")}
            onClick={
              verdict.subjectFilter
                ? () => onOpenRuns(verdict.subjectFilter ?? undefined)
                : undefined
            }
          >
            {verdict.subject}
          </LinkText>
        </h2>
        {verdict.aside ? (
          <LinkText
            className="ml-auto shrink-0 text-body tabular-nums text-foreground"
            onClick={
              verdict.asideFilter ? () => onOpenRuns(verdict.asideFilter ?? undefined) : undefined
            }
          >
            {verdict.aside}
          </LinkText>
        ) : null}
      </div>
      {verdict.evidence ? (
        <p className="ml-6 truncate text-body text-muted-foreground" title={verdict.evidence}>
          {verdict.evidence}
        </p>
      ) : null}
    </section>
  );
};

/** An experiment with no runs: what is missing, in order, with the one action each needs. */
const MissingSteps = ({
  experiment,
  hasWorkflow,
  onOpenWorkflow,
  onNewRun,
  onSweep,
}: Pick<
  ExperimentOverviewProps,
  "experiment" | "hasWorkflow" | "onOpenWorkflow" | "onNewRun" | "onSweep"
>): JSX.Element => {
  const cells = declaredCellCount(experiment.parameterSpace);
  const steps = [
    {
      key: "workflow",
      done: hasWorkflow,
      title: "Workflow",
      line: hasWorkflow
        ? experiment.workflowFile || experiment.workflowEntrypoint || "Bound"
        : "None bound · exp.define(wf) in Python, or open a workflow file",
      action: hasWorkflow ? null : (
        <DialogButton kind="secondary" onClick={onOpenWorkflow}>
          Open workflow…
        </DialogButton>
      ),
    },
    {
      key: "space",
      done: cells > 0,
      title: "Parameter space",
      line:
        cells > 0
          ? `${Object.keys(experiment.parameterSpace ?? {}).join(" × ")} · ${cells} combinations`
          : "Nothing declared · runs can still take parameters one by one",
      action:
        cells > 0 ? (
          <DialogButton kind="secondary" onClick={onSweep}>
            Sweep {cells}…
          </DialogButton>
        ) : null,
    },
    {
      key: "runs",
      done: false,
      title: "Runs",
      line: "0",
      action: (
        <DialogButton kind="secondary" onClick={onNewRun}>
          New run…
        </DialogButton>
      ),
    },
  ];
  return (
    <ol
      aria-label="What this experiment needs"
      className="max-w-[40rem] divide-y divide-border border-b border-border"
    >
      {steps.map((step) => (
        <li key={step.key} className="flex min-h-11 items-center gap-3 py-1">
          <StatusIcon status={step.done ? "succeeded" : "pending"} className="size-icon shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="block text-body text-foreground">{step.title}</span>
            <span className="block truncate text-label text-muted-foreground">{step.line}</span>
          </span>
          {step.action}
        </li>
      ))}
    </ol>
  );
};

/** Success · In flight · Duration, over the runs' latest attempts. Shared with the project (L02). */
export const Gauges = ({
  runs,
  rows,
  partial,
  onOpenRuns,
  label = "Experiment gauges",
}: {
  label?: string;
  /** Each run with its latest status. */
  runs: readonly { status: string }[];
  rows: readonly WorkspaceRunRow[];
  partial: boolean;
  onOpenRuns: (filter?: string) => void;
}): JSX.Element => {
  const counts = useMemo(() => countStatuses(runs.map((run) => run.status)), [runs]);
  const durations = useMemo(() => durationPointsOf(rows).map((point) => point.seconds), [rows]);
  const median = useMemo(
    () =>
      durations.length > 0
        ? quantile(
            [...durations].sort((left, right) => left - right),
            0.5,
          )
        : null,
    [durations],
  );
  const marks = useMemo(() => inFlightMarks(rows, median), [rows, median]);
  const openRun = useOpenRun(rows);
  // In flight is running + queued; a run that was never submitted is charted with
  // queued but is not in flight (the verdict's "n active" counts the same runs).
  const inFlight = useMemo(() => runs.filter((run) => isActiveStatus(run.status)).length, [runs]);
  const queued = inFlight - counts.running;
  return (
    <InstrumentStrip label={label}>
      <Instrument title="Success" inline>
        <span className="flex min-w-0 items-center gap-4">
          <SuccessDial counts={counts} onPick={(status) => onOpenRuns(`status:${status}`)} />
          <DialLegend counts={counts} unit={["run", "runs"]} partial={partial} />
        </span>
      </Instrument>
      <Instrument
        title="In flight"
        figure={inFlight}
        caption={`${counts.running} running · ${queued} queued`}
        onSelect={() => onOpenRuns("status:running,queued")}
        selectHint="Runs"
        selectLabel={`In flight: ${counts.running} running, ${queued} queued runs. Open them`}
      >
        <UnitMeter
          emptyLabel="Idle"
          label={`${counts.running} running, ${queued} queued`}
          marks={marks}
          reference={median !== null && counts.running > 0 ? 0.5 : undefined}
          onPick={openRun}
        />
      </Instrument>
      <Instrument
        title="Duration"
        figure={median === null ? "—" : formatSpan(median)}
        caption={median === null ? undefined : `median of ${durations.length} finished`}
      >
        {median === null ? (
          <span aria-hidden className="block h-5 border-b border-dashed border-border" />
        ) : (
          <DurationRange seconds={durations} />
        )}
      </Instrument>
    </InstrumentStrip>
  );
};

/** Outcome by a swept parameter or by task, and the key result on the swept axis. */
const Charts = ({
  experiment,
  runs,
  onOpenRuns,
  onPreviewRun,
}: {
  experiment: ExperimentSummary;
  runs: readonly RunSummary[];
  onOpenRuns: (filter?: string) => void;
  onPreviewRun: (runId: string) => void;
}): JSX.Element => {
  // Numeric swept axes first (the one with most values leads), then words.
  const axes = useMemo(() => {
    const keys = varyingParameterKeys(runs.map((run) => ({ parameters: run.parameters ?? {} })));
    const numeric = (key: string): number =>
      runs.every((run) => typeof (run.parameters?.[key] ?? 0) === "number") ? 1 : 0;
    const distinct = (key: string): number =>
      new Set(runs.map((run) => JSON.stringify(run.parameters?.[key]))).size;
    return [...keys].sort(
      (left, right) =>
        numeric(right) - numeric(left) ||
        distinct(right) - distinct(left) ||
        left.localeCompare(right),
    );
  }, [runs]);
  // `?by=task` (a task Preview's “Outcome in runs”, L06) opens the outcome by task.
  const [searchParams] = useSearchParams();
  const asked = searchParams.get("by");
  const [picked, setPicked] = useState<string | null>(asked === "task" ? TASK_AXIS : asked);
  const axis =
    picked && (picked === TASK_AXIS || axes.includes(picked)) ? picked : (axes[0] ?? TASK_AXIS);
  const tasks = useTaskOutcome(runs, axis === TASK_AXIS);
  const groups = useMemo(
    () =>
      axis === TASK_AXIS
        ? tasks.groups
        : outcomeByParameter(
            runs.map((run) => ({ id: run.id, status: run.status, parameters: run.parameters })),
            axis,
          ),
    [axis, runs, tasks.groups],
  );
  const { siblings, loading } = useRunSiblings(
    { id: "", experimentId: experiment.id },
    { results: true },
  );
  const sweep = useMemo(() => {
    const metric = keyMetric({ results: null }, siblings);
    return experimentSweep(siblings, metric);
  }, [siblings]);
  const choices = [
    ...axes.map((key) => ({ value: key, label: key })),
    { value: TASK_AXIS, label: "task" },
  ];
  return (
    <div className="grid min-w-0 gap-x-12 gap-y-8 lg:grid-cols-2">
      <GaugeSection
        title="Outcome"
        readout={
          axis === TASK_AXIS ? "latest attempt of each run, by task" : "latest attempt of each run"
        }
        control={
          choices.length > 1 ? (
            <ChoiceToggle label="Outcome by" value={axis} choices={choices} onChange={setPicked} />
          ) : undefined
        }
      >
        {groups.length === 0 ? (
          <p className="text-body text-muted-foreground">
            {axis === TASK_AXIS ? "No attempt has journalled tasks yet." : "No runs yet."}
          </p>
        ) : (
          <>
            <MixChart
              groups={groups}
              label={axis === TASK_AXIS ? "Outcome by task" : `Outcome by ${axis}`}
              wording={axis === TASK_AXIS ? TASK_WORDING : RUN_WORDING}
              onPick={
                axis === TASK_AXIS
                  ? undefined
                  : (id) => {
                      const value = (() => {
                        try {
                          return JSON.parse(id) as unknown;
                        } catch {
                          return undefined;
                        }
                      })();
                      if (value !== undefined) onOpenRuns(`${axis}:${String(value)}`);
                    }
              }
            />
            <StatusGlyphLegend className="pt-4" />
          </>
        )}
      </GaugeSection>
      {sweep ? (
        <GaugeSection
          title={`${sweep.metric} across ${sweep.axisKey}`}
          readout={`${sweep.siblingsWithResult} runs with a result`}
        >
          <SweepChart
            points={sweep.points}
            selfSeries={null}
            label={`${sweep.metric} of every run across ${sweep.axisKey}`}
            onPick={onPreviewRun}
          />
        </GaugeSection>
      ) : loading ? null : (
        <GaugeSection title="Key result">
          <p className="text-body text-muted-foreground">
            No run reported a numeric result on a swept parameter yet.
          </p>
        </GaugeSection>
      )}
    </div>
  );
};

export const ExperimentOverview = ({
  experiment,
  runs,
  rows,
  partial,
  hasWorkflow,
  onOpenRuns,
  onPreviewRun,
  onOpenWorkflow,
  onNewRun,
  onSweep,
}: ExperimentOverviewProps): JSX.Element => {
  const verdict = useMemo(
    () =>
      experimentVerdict(
        runs.map((run) => ({
          id: run.id,
          status: run.status,
          parameters: run.parameters,
          errorMessage: run.errorMessage,
        })),
        { declaredCells: declaredCellCount(experiment.parameterSpace) },
      ),
    [runs, experiment.parameterSpace],
  );
  return (
    <OverviewCanvas>
      <Verdict verdict={verdict} onOpenRuns={onOpenRuns} />
      {runs.length === 0 ? (
        <MissingSteps
          experiment={experiment}
          hasWorkflow={hasWorkflow}
          onOpenWorkflow={onOpenWorkflow}
          onNewRun={onNewRun}
          onSweep={onSweep}
        />
      ) : (
        <>
          <Gauges runs={runs} rows={rows} partial={partial} onOpenRuns={onOpenRuns} />
          <Charts
            experiment={experiment}
            runs={runs}
            onOpenRuns={onOpenRuns}
            onPreviewRun={onPreviewRun}
          />
        </>
      )}
    </OverviewCanvas>
  );
};
