/**
 * Everything MolPlot's view draws, derived from the attempt's reads and the
 * viewer's choices: the files list, the panels, the legend and the state.
 *
 * The reads are one TanStack query per attempt (`runKeys.metrics`): every
 * claimed file read by whichever contributed reader claims it, at the shared
 * step resolution (`STEP_INTERVAL`, thinned per series by the reader).
 */

import type { AttemptFile, RunAttempt } from "@molcrafts/molab-plugin";
import type { RunViewStateSpec } from "@molcrafts/molab-plugin/ui";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { journalRefetchInterval, runKeys } from "@/app/state/entityQueries";
import {
  type FigureSeries,
  figureSeries,
  fileColors,
  fileLabels,
  type GroupBy,
  groupPanels,
  type LegendEntry,
  legendOf,
  type PanelModel,
} from "./figure-model";
import { isFigureFile } from "./molplot-files";
import type { MolplotStyle } from "./panel-data";
import { type MetricsRead, readExecutionMetrics } from "./read-metrics";
import { STEP_INTERVAL } from "./resolution";
import { listTasks } from "./scalar-series";

/** One file of the view's list. */
export interface ViewFile {
  path: string;
  label: string;
  color: string;
  size: number | null;
  figure: boolean;
  /** The reader failed on it; it draws nothing. */
  error: string | null;
}

/**
 * The files the view lists: once read, the sources a reader actually took
 * (a name claim the content check rejected drops out), then the figures.
 * Before the read, every matched file.
 */
export const viewFiles = (
  files: readonly AttemptFile[],
  read: MetricsRead | undefined,
): ViewFile[] => {
  const figures = files.filter(isFigureFile).map((file) => file.relPath);
  const sources = read
    ? read.sources.map((source) => ({ path: source.path, error: source.error ?? null }))
    : files
        .filter((file) => !isFigureFile(file))
        .map((file) => ({ path: file.relPath, error: null }));
  const paths = [...sources.map((source) => source.path), ...figures];
  const colors = fileColors(paths);
  const labels = fileLabels(paths);
  const sizes = new Map(files.map((file) => [file.relPath, file.size ?? null]));
  const errors = new Map(sources.map((source) => [source.path, source.error]));
  return paths.map((path) => ({
    path,
    label: labels.get(path) ?? path,
    color: colors.get(path) ?? "",
    size: sizes.get(path) ?? null,
    figure: figures.includes(path),
    error: errors.get(path) ?? null,
  }));
};

interface StateInput {
  attempt: RunAttempt;
  pending: boolean;
  error: string | null;
  read: MetricsRead | undefined;
  allSeries: number;
  figures: number;
  drawn: number;
  task: string | null;
  retry: () => void;
}

/** Loading, failed, nothing to show — or null when there is a figure. */
export const figureState = (input: StateInput): RunViewStateSpec | null => {
  const { attempt, read, figures, retry } = input;
  if (input.pending) return { kind: "loading" };
  const failures = read?.sources.filter((source) => source.error) ?? [];
  const allFailed =
    read !== undefined && read.sources.length > 0 && failures.length === read.sources.length;
  if (figures === 0 && (input.error || allFailed)) {
    return {
      kind: "error",
      title: `MolPlot could not read ${attempt.executionId}`,
      detail: input.error ?? failures[0]?.error,
      onRetry: retry,
    };
  }
  if (input.allSeries === 0 && figures === 0) {
    return { kind: "empty", title: `No metrics in ${attempt.executionId}` };
  }
  if (input.drawn > 0) return null;
  return input.task
    ? { kind: "empty", title: `No metrics from ${input.task}`, detail: "Choose another task." }
    : { kind: "empty", title: "Nothing checked", detail: "Check a file to draw it." };
};

export interface MolplotFigure {
  files: ViewFile[];
  tasks: string[];
  /** Some series measured a wall clock. */
  timed: boolean;
  panels: PanelModel[];
  figures: ViewFile[];
  legend: LegendEntry[];
  state: RunViewStateSpec | null;
  /** The style as drawn: a task that is gone, or a Time axis nothing measured, falls back. */
  drawn: MolplotStyle;
}

const useAttemptMetrics = (attempt: RunAttempt) =>
  useQuery({
    queryKey: runKeys.metrics(
      attempt.projectId,
      attempt.experimentId,
      attempt.runId,
      attempt.executionId,
    ),
    queryFn: () => readExecutionMetrics(attempt, { stepInterval: STEP_INTERVAL }),
    refetchInterval: journalRefetchInterval(attempt.status),
    refetchIntervalInBackground: false,
  });

const drawable = (
  series: readonly FigureSeries[],
  checked: (path: string) => boolean,
  time: boolean,
): FigureSeries[] => series.filter((item) => checked(item.file) && (!time || item.timed));

export const useMolplotFigure = (
  attempt: RunAttempt,
  matched: readonly AttemptFile[],
  style: MolplotStyle,
  groupBy: GroupBy,
  unchecked: ReadonlySet<string>,
): MolplotFigure => {
  const query = useAttemptMetrics(attempt);
  const read = query.data;
  const files = useMemo(() => viewFiles(matched, read), [matched, read]);
  const tasks = useMemo(() => listTasks(read?.records ?? []), [read]);
  const task = style.task !== null && tasks.includes(style.task) ? style.task : null;
  const everySeries = useMemo(() => figureSeries(read?.sources ?? [], null), [read]);
  const series = useMemo(() => figureSeries(read?.sources ?? [], task), [read, task]);
  const timed = everySeries.some((item) => item.timed);
  const time = timed && style.x === "time";
  const panels = useMemo(() => {
    const colors = new Map(files.map((file) => [file.path, file.color]));
    const labels = new Map(files.map((file) => [file.path, file.label]));
    const shown = drawable(series, (path) => !unchecked.has(path), time);
    return groupPanels(shown, groupBy, colors, labels);
  }, [files, series, unchecked, time, groupBy]);
  const figures = files.filter((file) => file.figure && !unchecked.has(file.path));
  const drawnFiles = files.filter(
    (file) =>
      !unchecked.has(file.path) && (file.figure || series.some((s) => s.file === file.path)),
  );
  const legend = legendOf(
    groupBy,
    panels,
    drawnFiles.map((file) => ({ id: file.path, label: file.label, color: file.color })),
  );
  const state = figureState({
    attempt,
    pending: query.isPending,
    error: query.error
      ? query.error instanceof Error
        ? query.error.message
        : String(query.error)
      : null,
    read,
    allSeries: everySeries.length,
    figures: files.filter((file) => file.figure).length,
    drawn: panels.length + figures.length,
    task,
    retry: () => void query.refetch(),
  });
  const drawn = useMemo(
    (): MolplotStyle => ({ ...style, task, x: time ? "time" : "step" }),
    [style, task, time],
  );
  return { files, tasks, timed, panels, figures, legend, state, drawn };
};
