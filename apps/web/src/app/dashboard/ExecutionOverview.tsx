// ─────────────────────────────────────────────────────────────────────────────
// The Overview a scope opens with — the workspace Dashboard and a project's
// Overview tab share it, so both levels have one shape. Instruments only: a
// strip of four gauges, the activity clock, then the status mix and duration
// spread across the scope's children. Every list lives behind a tab.
//
// Every chart answers the same gestures: hover names a mark, click opens what
// it stands for, and two of them filter the rest — drag a window across the
// activity clock, or pick a backend. A filter strip says what is applied.
// ─────────────────────────────────────────────────────────────────────────────

import {
  Clock,
  FlaskConical,
  FolderKanban,
  Funnel,
  PlayCircle,
  Server,
  Sigma,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { type JSX, type ReactNode, useCallback, useMemo, useState } from "react";

import {
  DialLegend,
  DurationRange,
  formatSpan,
  GaugeSection,
  Instrument,
  InstrumentStrip,
  MixChart,
  OverviewColumn,
  quantile,
  StatusGlyphLegend,
  StatusTallies,
  SuccessDial,
  Tally,
  UnitMeter,
} from "@/app/components/entity";
import {
  ActivityPanel,
  attentionEdges,
  attentionMarks,
  attentionRuns,
  backendGroups,
  DurationsBy,
  durationPointsOf,
  EmptyLine,
  type GroupKey,
  inFlightMarks,
  rollupExecutions,
  statusGroupsBy,
  useOpenRun,
} from "@/app/dashboard/dashboardWidgets";
import {
  applyOverviewFilter,
  isFiltered,
  NO_FILTER,
  type OverviewFilter,
} from "@/app/dashboard/overviewFilter";
import { runPresentationStatus } from "@/app/runs/projections";
import { groupForStatus, type StatusGroupId } from "@/app/runs/statusGroups";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

/** Heading noun and readout noun for a grouping: "By project" · "3 projects". */
const groupWords = (key: GroupKey): { title: string; unit: readonly [string, string] } => {
  if (key === "project") return { title: "project", unit: ["project", "projects"] };
  if (key === "experiment") return { title: "experiment", unit: ["experiment", "experiments"] };
  return { title: key.slice("param:".length), unit: ["value", "values"] };
};

const plural = (count: number, [one, many]: readonly [string, string]): string =>
  count === 1 ? one : many;

const pad2 = (value: number): string => value.toString().padStart(2, "0");
const clock = (ms: number): string => {
  const date = new Date(ms);
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
};

const FilterStrip = ({
  filter,
  shown,
  total,
  onClear,
}: {
  filter: OverviewFilter;
  shown: number;
  total: number;
  onClear: () => void;
}): JSX.Element => (
  <div
    role="status"
    aria-label="Overview filter"
    className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 rounded-control bg-accent-muted px-3 py-1 text-label text-foreground"
  >
    <Funnel aria-hidden className="size-icon-sm text-accent" />
    {filter.window ? (
      <Tally
        icon={Clock}
        value={
          <span className="font-mono">
            {clock(filter.window[0])} – {clock(filter.window[1])}
          </span>
        }
        label={`Window ${clock(filter.window[0])} to ${clock(filter.window[1])}`}
      />
    ) : null}
    {filter.backend ? (
      <Tally icon={Server} value={filter.backend} label={`Backend ${filter.backend}`} />
    ) : null}
    <Tally
      icon={PlayCircle}
      value={`${shown}/${total}`}
      label={`${shown} of ${total} runs shown`}
      className="text-muted-foreground"
    />
    <WorkbenchIconAction label="Clear filter" className="ml-auto" onClick={onClear}>
      <X aria-hidden />
    </WorkbenchIconAction>
  </div>
);

/** The dashed rule's key: a dash and the duration it marks. */
const MedianKey = ({ seconds }: { seconds: number }): JSX.Element => (
  <span
    role="img"
    aria-label={`Dashed line: the median run, ${formatSpan(seconds)}`}
    title={`Dashed line: the median run, ${formatSpan(seconds)}`}
    className="inline-flex items-center gap-1 font-mono tabular-nums"
  >
    <span aria-hidden className="inline-block w-3 border-t border-dashed border-foreground/70" />
    <span aria-hidden>{formatSpan(seconds)}</span>
  </span>
);

const GROUP_ICON = { project: FolderKanban, experiment: FlaskConical, param: SlidersHorizontal };

interface ExecutionOverviewProps {
  rows: readonly WorkspaceRunRow[];
  /** The rows are a truncated page of the scope. */
  partial: boolean;
  /** Part of the inventory failed to load; an empty gauge must not claim quiet. */
  inventoryBlocked: boolean;
  /** The scope's children: projects of a workspace, experiments of a project, a parameter's values. */
  groupBy: GroupKey;
  /** Beside the "By …" heading: a choice of grouping, when there is one. */
  groupControl?: ReactNode;
  onGroupSelect?: (id: string) => void;
  onOpenAttention: () => void;
  onOpenTimeline: () => void;
  /** Visible names of the tabs the two summary gauges open. */
  attentionHint?: string;
  timelineHint?: string;
}

export const ExecutionOverview = ({
  rows,
  partial,
  inventoryBlocked,
  groupBy,
  groupControl,
  onGroupSelect,
  onOpenAttention,
  onOpenTimeline,
  attentionHint = "List",
  timelineHint = "Timeline",
}: ExecutionOverviewProps): JSX.Element => {
  const [filter, setFilter] = useState<OverviewFilter>(NO_FILTER);
  // The activity clock keeps its whole window as context for the brush.
  const byBackend = useMemo(
    () => applyOverviewFilter(rows, { window: null, backend: filter.backend }),
    [rows, filter.backend],
  );
  const scoped = useMemo(() => applyOverviewFilter(rows, filter), [rows, filter]);
  // Backends are counted before the backend pick, so the picked bar stays among its peers.
  const backends = useMemo(
    () => backendGroups(applyOverviewFilter(rows, { window: filter.window, backend: null })),
    [rows, filter.window],
  );

  const counts = useMemo(() => rollupExecutions(scoped), [scoped]);
  const flagged = useMemo(() => attentionRuns(scoped), [scoped]);
  const durations = useMemo(() => durationPointsOf(scoped).map((point) => point.seconds), [scoped]);
  const groups = useMemo(() => statusGroupsBy(scoped, groupBy), [scoped, groupBy]);
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
  const runningMarks = useMemo(() => inFlightMarks(scoped, median), [scoped, median]);
  const flaggedMarks = useMemo(() => attentionMarks(scoped), [scoped]);
  const openRun = useOpenRun(rows);

  const failedRuns = flagged.filter(
    (run) => groupForStatus(runPresentationStatus(run)) === "failed",
  ).length;
  const cancelledRuns = flagged.length - failedRuns;
  const inFlight = counts.running + counts.pending;
  const words = groupWords(groupBy);
  const edges = attentionEdges(scoped);

  const setWindow = useCallback(
    (window: [number, number] | null) => setFilter((current) => ({ ...current, window })),
    [],
  );
  const toggleBackend = useCallback(
    (backend: string) =>
      setFilter((current) => ({
        ...current,
        backend: current.backend === backend ? null : backend,
      })),
    [],
  );
  const pickOutcome = useCallback(
    (status: StatusGroupId) => {
      if (status === "failed" || status === "cancelled") onOpenAttention();
    },
    [onOpenAttention],
  );

  return (
    <OverviewColumn>
      {isFiltered(filter) ? (
        <FilterStrip
          filter={filter}
          shown={scoped.length}
          total={rows.length}
          onClear={() => setFilter(NO_FILTER)}
        />
      ) : null}

      <InstrumentStrip label="Execution gauges">
        <Instrument title="Success" inline>
          <span className="flex min-w-0 items-center gap-4">
            <SuccessDial counts={counts} onPick={pickOutcome} />
            <DialLegend counts={counts} partial={partial} />
          </span>
        </Instrument>

        <Instrument
          title="In flight"
          figure={inFlight}
          caption={
            <StatusTallies
              counts={counts}
              statuses={["running", "pending"]}
              unit="executions"
              keepZero
            />
          }
          onSelect={onOpenTimeline}
          selectHint={timelineHint}
          selectLabel={`In flight: ${counts.running} running, ${counts.pending} queued executions. Open the timeline`}
        >
          <UnitMeter
            emptyLabel="Idle"
            label={`${counts.running} running, ${counts.pending} queued`}
            marks={runningMarks}
            reference={median !== null && counts.running > 0 ? 0.5 : undefined}
            note={
              median !== null && counts.running > 0 ? <MedianKey seconds={median} /> : undefined
            }
            onPick={openRun}
          />
        </Instrument>

        <Instrument
          title="Needs attention"
          figure={
            <span className={cn(flagged.length > 0 && "text-status-failed-foreground")}>
              {flagged.length}
            </span>
          }
          caption={
            <StatusTallies
              counts={{ ...counts, failed: failedRuns, cancelled: cancelledRuns }}
              statuses={["failed", "cancelled"]}
              unit="runs"
              keepZero
            />
          }
          onSelect={onOpenAttention}
          selectHint={attentionHint}
          selectLabel={`${flagged.length} ${plural(flagged.length, ["run needs", "runs need"])} attention. Open the list`}
        >
          <UnitMeter
            emptyLabel={inventoryBlocked ? "Inventory incomplete" : "All clear"}
            label={`${failedRuns} failed and ${cancelledRuns} cancelled runs, newest first`}
            marks={flaggedMarks}
            note={
              edges ? (
                <Tally
                  icon={Clock}
                  value={`${edges[0]} → ${edges[1]}`}
                  label={`Newest ${edges[0]} ago, oldest ${edges[1]}`}
                  className="font-mono"
                />
              ) : undefined
            }
            onPick={openRun}
          />
        </Instrument>

        <Instrument
          title="Run duration"
          figure={median === null ? "—" : formatSpan(median)}
          caption={
            median === null ? undefined : (
              <Tally
                icon={Sigma}
                value={durations.length}
                label={`Median of ${durations.length} finished ${plural(durations.length, ["run", "runs"])}`}
              />
            )
          }
        >
          {median === null ? (
            <span aria-hidden className="block h-5 border-b border-dashed border-border" />
          ) : (
            <DurationRange seconds={durations} />
          )}
        </Instrument>
      </InstrumentStrip>

      <ActivityPanel
        rows={byBackend}
        inventoryBlocked={inventoryBlocked}
        selection={filter.window}
        onSelect={setWindow}
      />

      <div className="grid min-w-0 gap-x-16 gap-y-12 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <GaugeSection
          title={`By ${words.title}`}
          control={groupControl}
          readout={
            <Tally
              icon={
                GROUP_ICON[
                  groupBy.startsWith("param:") ? "param" : (groupBy as "project" | "experiment")
                ]
              }
              value={groups.length}
              label={`${groups.length} ${plural(groups.length, words.unit)}`}
            />
          }
        >
          {groups.length === 0 ? (
            <EmptyLine>No executions in this view.</EmptyLine>
          ) : (
            <>
              <MixChart
                groups={groups}
                label={`Execution status by ${words.title}`}
                onPick={onGroupSelect}
              />
              <StatusGlyphLegend className="pt-4" />
            </>
          )}
        </GaugeSection>
        <GaugeSection
          title="Backends"
          readout={
            <Tally
              icon={Server}
              value={backends.length}
              label={`${backends.length} ${plural(backends.length, ["backend", "backends"])}`}
            />
          }
        >
          {backends.length === 0 ? (
            <EmptyLine>No executor recorded yet.</EmptyLine>
          ) : (
            <MixChart
              groups={backends}
              label="Execution status by backend"
              selected={filter.backend}
              onPick={toggleBackend}
            />
          )}
        </GaugeSection>
      </div>

      <GaugeSection title={`Duration by ${words.title}`}>
        <DurationsBy rows={scoped} groupBy={groupBy} />
      </GaugeSection>
    </OverviewColumn>
  );
};
